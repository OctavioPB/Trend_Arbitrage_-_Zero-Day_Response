"""LinkedIn producer — polls company posts via RapidAPI and publishes raw events.

Primary path: RapidAPI LinkedIn data endpoint (requires RAPIDAPI_KEY).
Fallback: when quota is exhausted (HTTP 429), the producer backs off and
retries on the next cycle rather than crashing. LinkedIn does not expose
a public RSS feed, so there is no secondary feed fallback.

Deduplication:
    URL hash via SeenURLCache (Redis-backed, 24-hour TTL).

Config via environment:
    RAPIDAPI_KEY               RapidAPI key (required)
    LINKEDIN_COMPANY_HANDLES   comma-separated company slugs, e.g. "google,meta,openai"
    LINKEDIN_POLL_INTERVAL     seconds between full sweep of all handles (default 600)
    LINKEDIN_POSTS_PER_HANDLE  max posts to fetch per company per cycle (default 10)
"""

import logging
import os
import time
from datetime import datetime, timezone

import requests

from ingestion.config.kafka_config import TOPIC_RAW, create_producer, publish_with_retry
from ingestion.dedup import SeenURLCache
from ingestion.models import RawEvent, make_event_id

logger = logging.getLogger(__name__)

# RapidAPI endpoint for LinkedIn company posts
# Docs: https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-scraper
_RAPIDAPI_HOST = "linkedin-data-scraper.p.rapidapi.com"
_POSTS_ENDPOINT = f"https://{_RAPIDAPI_HOST}/company_updates"
_REQUEST_TIMEOUT = 15
_MAX_TEXT_CHARS = 8_000

# After a 429, wait this many seconds before the next attempt for that handle
_RATE_LIMIT_BACKOFF = 120


class LinkedInProducer:
    """Polls LinkedIn company posts via RapidAPI and publishes new posts to Kafka."""

    def __init__(self) -> None:
        self._api_key = os.environ.get("RAPIDAPI_KEY", "")
        if not self._api_key:
            logger.warning(
                "RAPIDAPI_KEY is not set — LinkedInProducer will not fetch any data. "
                "Set RAPIDAPI_KEY to enable LinkedIn ingestion."
            )

        self._handles: list[str] = [
            h.strip()
            for h in os.environ.get("LINKEDIN_COMPANY_HANDLES", "").split(",")
            if h.strip()
        ]
        if not self._handles:
            logger.warning(
                "LINKEDIN_COMPANY_HANDLES is not set — no companies to watch. "
                "Set it to a comma-separated list of LinkedIn company slugs."
            )

        self._interval = int(os.environ.get("LINKEDIN_POLL_INTERVAL", "600"))
        self._posts_per_handle = int(os.environ.get("LINKEDIN_POSTS_PER_HANDLE", "10"))

        self._producer = create_producer()
        self._seen = SeenURLCache(prefix="linkedin")
        # Track per-handle rate-limit cooldown
        self._rate_limited_until: dict[str, float] = {}

        logger.info(
            "LinkedInProducer ready — handles=%s interval=%ds posts_per_handle=%d",
            self._handles,
            self._interval,
            self._posts_per_handle,
        )

    def run(self) -> None:
        """Poll all handles in a loop. Never raises."""
        logger.info("LinkedInProducer starting")
        while True:
            if not self._api_key or not self._handles:
                time.sleep(self._interval)
                continue

            published = 0
            for handle in self._handles:
                try:
                    published += self._poll_handle(handle)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Unexpected error polling LinkedIn handle %r: %s", handle, exc)

            logger.info("LinkedInProducer cycle — %d new event(s) published", published)
            time.sleep(self._interval)

    # ── Private ───────────────────────────────────────────────────────────────

    def _poll_handle(self, handle: str) -> int:
        now_ts = time.monotonic()
        cooldown_until = self._rate_limited_until.get(handle, 0.0)
        if now_ts < cooldown_until:
            remaining = cooldown_until - now_ts
            logger.debug("LinkedIn handle %r is rate-limited — %.0fs remaining", handle, remaining)
            return 0

        try:
            resp = requests.get(
                _POSTS_ENDPOINT,
                headers={
                    "x-rapidapi-host": _RAPIDAPI_HOST,
                    "x-rapidapi-key": self._api_key,
                },
                params={"company_url": f"https://www.linkedin.com/company/{handle}/"},
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.error("LinkedIn request failed for handle %r: %s", handle, exc)
            return 0

        if resp.status_code == 429:
            logger.warning(
                "LinkedIn API rate limit for handle %r — backing off %ds",
                handle,
                _RATE_LIMIT_BACKOFF,
            )
            self._rate_limited_until[handle] = now_ts + _RATE_LIMIT_BACKOFF
            return 0

        if resp.status_code == 401:
            logger.error(
                "LinkedIn API authentication failed (handle=%r) — check RAPIDAPI_KEY",
                handle,
            )
            return 0

        if resp.status_code != 200:
            logger.error(
                "LinkedIn API returned %d for handle %r: %s",
                resp.status_code,
                handle,
                resp.text[:200],
            )
            return 0

        try:
            data = resp.json()
        except ValueError as exc:
            logger.warning("LinkedIn response not valid JSON for handle %r: %s", handle, exc)
            return 0

        posts = self._extract_posts(data)
        return self._publish_posts(posts, handle)

    def _extract_posts(self, data: dict | list) -> list[dict]:
        """Normalise RapidAPI response to a flat list of post dicts."""
        if isinstance(data, list):
            return data[: self._posts_per_handle]
        if isinstance(data, dict):
            for key in ("updates", "posts", "data", "items", "results"):
                if isinstance(data.get(key), list):
                    return data[key][: self._posts_per_handle]
        return []

    def _publish_posts(self, posts: list[dict], handle: str) -> int:
        published = 0
        for post in posts:
            url = self._extract_url(post, handle)
            if not url or self._seen.is_seen(url):
                continue

            event = self._build_event(post, url, handle)
            publish_with_retry(
                self._producer,
                TOPIC_RAW,
                event.to_kafka_payload(),
                key=event.event_id,
            )
            self._seen.mark_seen(url)
            published += 1

        return published

    def _extract_url(self, post: dict, handle: str) -> str:
        """Return the canonical URL for the post; fall back to a synthetic one."""
        for key in ("url", "postUrl", "post_url", "link", "shareUrl"):
            val = post.get(key)
            if val and isinstance(val, str):
                return val
        post_id = post.get("id") or post.get("postId") or post.get("urn", "")
        if post_id:
            return f"https://www.linkedin.com/feed/update/{post_id}/"
        return ""

    def _build_event(self, post: dict, url: str, handle: str) -> RawEvent:
        text = ""
        for key in ("text", "commentary", "content", "description", "body"):
            val = post.get(key)
            if isinstance(val, str) and val.strip():
                text = val.strip()[:_MAX_TEXT_CHARS]
                break

        author = post.get("actor") or post.get("author") or post.get("company") or handle

        created_at_raw = (
            post.get("createdAt") or post.get("created_at") or post.get("postedDate")
        )
        if created_at_raw:
            try:
                if isinstance(created_at_raw, (int, float)):
                    # Unix ms timestamp
                    ts_sec = created_at_raw / 1000 if created_at_raw > 1e10 else created_at_raw
                    collected_at = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
                else:
                    dt = datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00"))
                    collected_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except (ValueError, OSError, OverflowError):
                collected_at = datetime.now(tz=timezone.utc)
        else:
            collected_at = datetime.now(tz=timezone.utc)

        likes = int(post.get("likes") or post.get("likeCount") or post.get("numLikes") or 0)
        comments = int(post.get("comments") or post.get("commentCount") or post.get("numComments") or 0)

        return RawEvent(
            event_id=make_event_id("linkedin", url),
            source="linkedin",
            collected_at=collected_at,
            raw_text=text,
            url=url,
            author=str(author),
            engagement_score=float(likes + comments),
            metadata={
                "company_handle": handle,
                "likes": likes,
                "comments": comments,
            },
        )


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    LinkedInProducer().run()
