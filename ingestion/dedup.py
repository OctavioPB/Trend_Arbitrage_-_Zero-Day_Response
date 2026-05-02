"""URL deduplication cache — prevents re-publishing the same content across poll cycles.

Uses Redis with a 24-hour TTL as the primary store. Falls back to an
in-memory set if Redis is unavailable; the in-memory fallback deduplicates
within a single process lifetime only and logs a warning on startup.

Usage:
    cache = SeenURLCache(prefix="news")
    if not cache.is_seen(url):
        cache.mark_seen(url)
        # publish event
"""

from __future__ import annotations

import logging
import os

from ingestion.models import make_event_id

logger = logging.getLogger(__name__)

_TTL_SECONDS = 86_400  # 24 hours
_KEY_PREFIX = "trend:seen"


class SeenURLCache:
    """Redis-backed dedup set keyed by deterministic UUID5 of source + URL.

    The Redis key format is:  trend:seen:{prefix}:{uuid5}
    TTL is reset to _TTL_SECONDS on every mark_seen call.
    """

    def __init__(self, prefix: str, ttl_seconds: int = _TTL_SECONDS) -> None:
        self._prefix = prefix
        self._ttl = ttl_seconds
        self._redis = self._connect_redis()
        self._memory: set[str] = set()  # used only when Redis is unavailable

    # ── Public API ────────────────────────────────────────────────────────────

    def is_seen(self, url: str) -> bool:
        """Return True if this URL was published in the last TTL window."""
        key = self._make_key(url)
        if self._redis is not None:
            try:
                return bool(self._redis.exists(key))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis read error in SeenURLCache: %s — using memory", exc)
        return key in self._memory

    def mark_seen(self, url: str) -> None:
        """Record the URL as published. Resets TTL if already present."""
        key = self._make_key(url)
        if self._redis is not None:
            try:
                self._redis.setex(key, self._ttl, "1")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis write error in SeenURLCache: %s — using memory", exc)
        self._memory.add(key)

    # ── Private ───────────────────────────────────────────────────────────────

    def _make_key(self, url: str) -> str:
        uid = make_event_id(self._prefix, url)
        return f"{_KEY_PREFIX}:{self._prefix}:{uid}"

    @staticmethod
    def _connect_redis():
        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            logger.warning(
                "REDIS_URL not set — SeenURLCache will use in-memory fallback "
                "(dedup resets on process restart)"
            )
            return None
        try:
            import redis

            client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
            client.ping()
            logger.debug("SeenURLCache connected to Redis at %s", redis_url)
            return client
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "SeenURLCache could not connect to Redis (%s) — using in-memory fallback",
                exc,
            )
            return None
