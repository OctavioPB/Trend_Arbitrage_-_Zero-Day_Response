"""Unit tests for api.auth and api.middleware.rate_limit.

All DB and Redis I/O is mocked. These tests never hit the network or DB.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import api.auth as auth_module
from api.auth import (
    create_access_token,
    decode_token,
    generate_api_key,
    require_scope,
    verify_api_key,
)
from api.middleware.rate_limit import RateLimitMiddleware


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_request(token: str | None = None, method: str = "GET", path: str = "/signals") -> MagicMock:
    """Build a mock Request with an optional Authorization header."""
    req = MagicMock()
    req.method = method
    req.url.path = path
    if req.client:
        req.client.host = "127.0.0.1"
    else:
        req.client = MagicMock()
        req.client.host = "127.0.0.1"

    def _headers_get(key, default=""):
        if key == "Authorization" and token:
            return f"Bearer {token}"
        return default

    req.headers.get.side_effect = _headers_get
    return req


def _valid_token(scopes: list[str] | None = None) -> str:
    return create_access_token(subject="testuser", scopes=scopes or ["read:signals"])


# ── Token creation & decoding ─────────────────────────────────────────────────


class TestTokenRoundtrip:
    def test_decode_returns_sub_and_scopes(self):
        token = create_access_token("alice", ["read:signals", "read:segments"])
        payload = decode_token(token)
        assert payload["sub"] == "alice"
        assert "read:signals" in payload["scopes"]
        assert "read:segments" in payload["scopes"]

    def test_decode_raises_401_on_tampered_signature(self):
        token = create_access_token("alice", ["read:signals"])
        tampered = token[:-4] + "XXXX"
        with pytest.raises(HTTPException) as exc:
            decode_token(tampered)
        assert exc.value.status_code == 401

    def test_decode_raises_401_on_expired_token(self):
        with patch.object(auth_module, "ACCESS_TOKEN_EXPIRE_MINUTES", -1):
            token = create_access_token("alice", ["read:signals"])
        with pytest.raises(HTTPException) as exc:
            decode_token(token)
        assert exc.value.status_code == 401

    def test_decode_raises_401_on_missing_sub(self):
        from jose import jwt as jose_jwt
        payload = {"scopes": ["read:signals"]}
        token = jose_jwt.encode(payload, auth_module.SECRET_KEY, algorithm=auth_module.ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            decode_token(token)
        assert exc.value.status_code == 401


# ── require_scope — JWT path ──────────────────────────────────────────────────


class TestRequireScopeJWT:
    def test_valid_scope_returns_subject(self):
        token = _valid_token(["read:signals"])
        dep = require_scope("read:signals")
        result = dep(_make_request(token))
        assert result == "testuser"

    def test_wrong_scope_raises_403(self):
        token = _valid_token(["read:signals"])
        dep = require_scope("write:alerts")
        with pytest.raises(HTTPException) as exc:
            dep(_make_request(token))
        assert exc.value.status_code == 403

    def test_no_authorization_header_raises_401(self):
        dep = require_scope("read:signals")
        with pytest.raises(HTTPException) as exc:
            dep(_make_request(token=None))
        assert exc.value.status_code == 401

    def test_malformed_jwt_raises_401(self):
        dep = require_scope("read:signals")
        with pytest.raises(HTTPException) as exc:
            dep(_make_request(token="not-a-ta-key-but-invalid-jwt"))
        assert exc.value.status_code == 401

    def test_multi_scope_token_satisfies_any_scope(self):
        token = create_access_token("alice", ["read:signals", "write:alerts"])
        for scope in ["read:signals", "write:alerts"]:
            result = require_scope(scope)(_make_request(token))
            assert result == "alice"


# ── require_scope — API key path ──────────────────────────────────────────────


class TestRequireScopeAPIKey:
    def _make_key_candidate(self, scopes: list[str], revoked: bool = False) -> tuple[str, dict]:
        plain, hashed = generate_api_key()
        candidate = {
            "id": "key-id-001",
            "key_hash": hashed,
            "owner": "service-account",
            "scopes": scopes,
            "revoked": revoked,
        }
        return plain, candidate

    def test_valid_key_with_correct_scope_returns_owner(self):
        plain, candidate = self._make_key_candidate(["read:signals"])
        dep = require_scope("read:signals")

        with patch.object(auth_module, "_lookup_api_key_candidates", return_value=[candidate]):
            with patch.object(auth_module, "stamp_api_key_used"):
                result = dep(_make_request(token=plain))

        assert result == "service-account"

    def test_valid_key_wrong_scope_raises_403(self):
        plain, candidate = self._make_key_candidate(["read:signals"])
        dep = require_scope("write:alerts")

        with patch.object(auth_module, "_lookup_api_key_candidates", return_value=[candidate]):
            with pytest.raises(HTTPException) as exc:
                dep(_make_request(token=plain))

        assert exc.value.status_code == 403

    def test_no_matching_candidates_raises_401(self):
        plain, _ = self._make_key_candidate(["read:signals"])
        dep = require_scope("read:signals")

        with patch.object(auth_module, "_lookup_api_key_candidates", return_value=[]):
            with pytest.raises(HTTPException) as exc:
                dep(_make_request(token=plain))

        assert exc.value.status_code == 401

    def test_bcrypt_mismatch_raises_401(self):
        plain, _ = self._make_key_candidate(["read:signals"])
        _, other_candidate = self._make_key_candidate(["read:signals"])
        dep = require_scope("read:signals")

        # candidate has a different key hash — bcrypt verify will fail
        with patch.object(auth_module, "_lookup_api_key_candidates", return_value=[other_candidate]):
            with pytest.raises(HTTPException) as exc:
                dep(_make_request(token=plain))

        assert exc.value.status_code == 401

    def test_stamp_api_key_used_called_on_success(self):
        plain, candidate = self._make_key_candidate(["read:signals"])
        dep = require_scope("read:signals")

        with patch.object(auth_module, "_lookup_api_key_candidates", return_value=[candidate]):
            with patch.object(auth_module, "stamp_api_key_used") as mock_stamp:
                dep(_make_request(token=plain))
                mock_stamp.assert_called_once_with("key-id-001")


# ── generate_api_key + verify_api_key ─────────────────────────────────────────


class TestApiKeyHelpers:
    def test_generate_returns_two_strings(self):
        plain, hashed = generate_api_key()
        assert isinstance(plain, str)
        assert isinstance(hashed, str)

    def test_plain_key_starts_with_ta_prefix(self):
        plain, _ = generate_api_key()
        assert plain.startswith("ta_")

    def test_verify_returns_true_for_matching_pair(self):
        plain, hashed = generate_api_key()
        assert verify_api_key(plain, hashed) is True

    def test_verify_returns_false_for_wrong_key(self):
        _, hashed = generate_api_key()
        wrong, _ = generate_api_key()
        assert verify_api_key(wrong, hashed) is False

    def test_two_keys_are_always_distinct(self):
        k1, _ = generate_api_key()
        k2, _ = generate_api_key()
        assert k1 != k2


# ── RateLimitMiddleware ────────────────────────────────────────────────────────


def _mock_response():
    resp = MagicMock()
    resp.headers = {}
    resp.status_code = 200
    return resp


class TestRateLimitMiddleware:
    def _make_http_request(
        self, path: str = "/signals", method: str = "GET", ip: str = "10.0.0.1"
    ) -> MagicMock:
        req = MagicMock()
        req.url.path = path
        req.method = method
        req.client = MagicMock()
        req.client.host = ip
        return req

    def _build_middleware(self, rpm: int = 60, write_rpm: int = 20, redis_client=None) -> RateLimitMiddleware:
        with patch("api.middleware.rate_limit._connect_redis", return_value=redis_client):
            return RateLimitMiddleware(
                app=MagicMock(),
                requests_per_minute=rpm,
                write_per_minute=write_rpm,
            )

    def test_under_limit_adds_rate_limit_headers(self):
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 1
        middleware = self._build_middleware(rpm=60, redis_client=mock_redis)

        mock_resp = _mock_response()
        call_next = AsyncMock(return_value=mock_resp)

        async def _run():
            return await middleware.dispatch(self._make_http_request(), call_next)

        result = asyncio.run(_run())
        call_next.assert_called_once()
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers

    def test_over_limit_returns_429(self):
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 61  # exceeds rpm=60
        middleware = self._build_middleware(rpm=60, redis_client=mock_redis)

        call_next = AsyncMock()

        async def _run():
            return await middleware.dispatch(self._make_http_request(), call_next)

        result = asyncio.run(_run())
        assert result.status_code == 429
        call_next.assert_not_called()

    def test_429_includes_retry_after_header(self):
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 999
        middleware = self._build_middleware(rpm=60, redis_client=mock_redis)

        async def _run():
            return await middleware.dispatch(self._make_http_request(), AsyncMock())

        result = asyncio.run(_run())
        assert "Retry-After" in result.headers

    def test_exempt_path_bypasses_rate_limit(self):
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 999
        middleware = self._build_middleware(rpm=60, redis_client=mock_redis)

        call_next = AsyncMock(return_value=_mock_response())

        async def _run():
            return await middleware.dispatch(
                self._make_http_request(path="/health"), call_next
            )

        asyncio.run(_run())
        call_next.assert_called_once()
        mock_redis.incr.assert_not_called()

    def test_redis_unavailable_bypasses_rate_limiting(self):
        middleware = self._build_middleware(redis_client=None)
        assert middleware._redis is None

        call_next = AsyncMock(return_value=_mock_response())

        async def _run():
            return await middleware.dispatch(self._make_http_request(), call_next)

        asyncio.run(_run())
        call_next.assert_called_once()

    def test_write_methods_use_write_limit(self):
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 21  # exceeds write_rpm=20 but not rpm=60
        middleware = self._build_middleware(rpm=60, write_rpm=20, redis_client=mock_redis)

        async def _run():
            return await middleware.dispatch(
                self._make_http_request(method="POST"), AsyncMock()
            )

        result = asyncio.run(_run())
        assert result.status_code == 429

    def test_write_under_write_limit_passes(self):
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 5  # under write_rpm=20
        middleware = self._build_middleware(rpm=60, write_rpm=20, redis_client=mock_redis)

        call_next = AsyncMock(return_value=_mock_response())

        async def _run():
            return await middleware.dispatch(
                self._make_http_request(method="DELETE"), call_next
            )

        asyncio.run(_run())
        call_next.assert_called_once()

    def test_redis_error_during_request_bypasses(self):
        mock_redis = MagicMock()
        mock_redis.incr.side_effect = ConnectionError("Redis gone")
        middleware = self._build_middleware(rpm=60, redis_client=mock_redis)

        call_next = AsyncMock(return_value=_mock_response())

        async def _run():
            return await middleware.dispatch(self._make_http_request(), call_next)

        asyncio.run(_run())
        call_next.assert_called_once()
