"""Fixed-window rate limiter middleware backed by Redis.

Algorithm: per-IP, per-minute fixed window.
  key  = trend:rl:{client_ip}:{minute_bucket}
  value = INCR (atomic); EXPIRE 120s set on creation
  limit = RATE_LIMIT_PER_MINUTE for GET/HEAD/OPTIONS
        = RATE_LIMIT_WRITE_PER_MINUTE for POST/PUT/PATCH/DELETE

Degradation: if Redis is unavailable at startup or at request time,
rate limiting is bypassed with a warning. The API remains available.

Response headers on every non-bypassed request:
  X-RateLimit-Limit:      configured limit for this request type
  X-RateLimit-Remaining:  tokens remaining in current window
  Retry-After:            seconds until window resets (only on 429)
  X-RateLimit-Reset:      Unix timestamp when the window resets
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Paths exempt from rate limiting
_EXEMPT = {"/health", "/openapi.json", "/docs", "/redoc"}

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _connect_redis():
    url = os.environ.get("REDIS_URL", "")
    if not url:
        logger.warning("REDIS_URL not set — rate limiting disabled")
        return None
    try:
        import redis

        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        return client
    except Exception as exc:
        logger.warning("Rate limiter: cannot connect to Redis (%s) — disabled", exc)
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP fixed-window rate limiter."""

    def __init__(
        self,
        app,
        requests_per_minute: int | None = None,
        write_per_minute: int | None = None,
    ) -> None:
        super().__init__(app)
        self._rpm = requests_per_minute or int(
            os.environ.get("RATE_LIMIT_PER_MINUTE", "60")
        )
        self._write_rpm = write_per_minute or int(
            os.environ.get("RATE_LIMIT_WRITE_PER_MINUTE", "20")
        )
        self._redis = _connect_redis()
        if self._redis:
            logger.info(
                "RateLimitMiddleware ready — GET=%d/min, write=%d/min",
                self._rpm,
                self._write_rpm,
            )

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT or self._redis is None:
            return await call_next(request)

        is_write = request.method in _WRITE_METHODS
        limit = self._write_rpm if is_write else self._rpm

        client_ip = (request.client.host if request.client else "unknown")
        now = int(time.time())
        window_bucket = now // 60
        key = f"trend:rl:{client_ip}:{window_bucket}"

        try:
            count = self._redis.incr(key)
            if count == 1:
                # Set TTL only on creation; 120s covers the current + next window
                self._redis.expire(key, 120)
        except Exception as exc:
            logger.warning("Rate limiter Redis error: %s — bypassing", exc)
            return await call_next(request)

        remaining = max(0, limit - count)
        seconds_in_window = now % 60
        retry_after = 60 - seconds_in_window
        reset_ts = now + retry_after

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again in the next minute.",
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response
