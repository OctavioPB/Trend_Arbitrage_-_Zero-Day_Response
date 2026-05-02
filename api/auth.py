"""Authentication core — JWT access tokens + scoped API key validation.

Token identification (both use Authorization: Bearer):
  JWT:     does not start with 'ta_'; decoded in-process, no DB round-trip.
  API key: starts with 'ta_'; looked up via key_prefix index + bcrypt verify.

Scopes:
  read:signals   — GET /signals, /mpi, /history
  read:segments  — GET /segments, /alerts
  write:alerts   — POST / DELETE /alerts

Dependency factory:
  require_scope("read:signals") → FastAPI Depends-compatible callable
  Returns the authenticated subject (username or API key owner) on success.
  Raises HTTP 401 / 403 on failure.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt as _bcrypt
from fastapi import HTTPException, Request
from jose import JWTError, jwt

from api.db import get_conn

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SECRET_KEY: str = os.environ.get(
    "API_SECRET_KEY",
    "insecure-dev-secret-change-me-in-production",
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

ADMIN_USER: str = os.environ.get("API_ADMIN_USER", "admin")
ADMIN_PASSWORD: str = os.environ.get("API_ADMIN_PASSWORD", "")

_API_KEY_PREFIX = "ta_"
_KEY_PREFIX_LEN = 12  # chars stored in api_keys.key_prefix for index lookup

SCOPES: dict[str, str] = {
    "read:signals": "Read /signals, /mpi, /history endpoints",
    "read:segments": "Read /segments and /alerts endpoints",
    "write:alerts": "Create and delete alert rules",
}

# ── JWT helpers ───────────────────────────────────────────────────────────────


def create_access_token(subject: str, scopes: list[str]) -> str:
    """Issue a signed JWT with the given subject and scopes."""
    expire = datetime.now(tz=timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "scopes": scopes,
        "exp": expire,
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises HTTP 401 on any failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail="Token invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── API key helpers ───────────────────────────────────────────────────────────


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key.

    Returns:
        (plain_key, key_hash) where plain_key is shown once to the user
        and key_hash is stored in the database.
    """
    plain = _API_KEY_PREFIX + secrets.token_urlsafe(32)
    hashed = _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()
    return plain, hashed


def verify_api_key(plain: str, hashed: str) -> bool:
    """Return True if plain matches hashed (bcrypt)."""
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── DB helpers ────────────────────────────────────────────────────────────────


def _lookup_api_key_candidates(key_prefix: str) -> list[dict]:
    """Return non-revoked api_keys rows whose key_prefix matches."""
    sql = """
        SELECT id::text, key_hash, owner, scopes, revoked, expires_at
        FROM api_keys
        WHERE key_prefix = %s
          AND revoked = false
          AND (expires_at IS NULL OR expires_at > NOW())
    """
    try:
        with get_conn() as conn:
            import psycopg2.extras

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (key_prefix,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.error("API key lookup failed: %s", exc)
        return []


def stamp_api_key_used(key_id: str) -> None:
    """Update last_used_at for the given key. Best-effort; never raises."""
    sql = "UPDATE api_keys SET last_used_at = NOW() WHERE id = %s::uuid"
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (key_id,))
            conn.commit()
    except Exception as exc:
        logger.warning("Failed to stamp API key last_used_at: %s", exc)


# ── Scope enforcement ─────────────────────────────────────────────────────────


def _check_scope(token_scopes: list[str], required: str) -> None:
    if required not in token_scopes:
        raise HTTPException(
            status_code=403,
            detail=f"Scope '{required}' required; token has {token_scopes}",
        )


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def require_scope(required_scope: str):
    """Return a FastAPI dependency that validates the caller has required_scope.

    Supports both JWT Bearer tokens and ta_* API keys in the same header.
    Returns the authenticated subject string on success.
    """
    def _dep(request: Request) -> str:
        token = _extract_bearer(request)
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated — provide Authorization: Bearer <token>",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # JWT path: fast, no DB
        if not token.startswith(_API_KEY_PREFIX):
            payload = decode_token(token)
            _check_scope(payload.get("scopes", []), required_scope)
            return payload["sub"]

        # API key path: prefix lookup + bcrypt verify
        prefix = token[:_KEY_PREFIX_LEN]
        candidates = _lookup_api_key_candidates(prefix)

        for candidate in candidates:
            if verify_api_key(token, candidate["key_hash"]):
                _check_scope(list(candidate["scopes"] or []), required_scope)
                stamp_api_key_used(candidate["id"])
                return candidate["owner"]

        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _dep
