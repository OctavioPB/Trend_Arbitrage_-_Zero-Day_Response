"""News producer — NewsAPI + GDELT integration for industry and competitor signals.

Two sources in priority order:
  1. NewsAPI (/v2/everything) — requires NEWSAPI_KEY; up to 100 results per call
  2. GDELT 2.0 Doc API — no auth required; publicly accessible

Deduplication:
    URL hash via SeenURLCache (Redis-backed, 24-hour TTL).

Config via environment:
    NEWSAPI_KEY           NewsAPI.org API key (required for NewsAPI source)
    NEWS_KEYWORDS         comma-separated keyword/phrase list to query (required)
    NEWS_POLL_INTERVAL    seconds between poll cycles (default 300)
    NEWSAPI_LANGUAGE      ISO 639-1 language code (default "en")
    NEWSAPI_PAGE_SIZE     results per NewsAPI request, 1–100 (default 50)
    GDELT_ENABLED         set to "false" to disable GDELT (default "true")
    GDELT_MAX_RECORDS     max articles per GDELT query (default 25)
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

from ingestion.config.kafka_config import TOPIC_RAW, create_producer, publish_with_retry
from ingestion.dedup import SeenURLCache
from ingestion.models import RawEvent, make_event_id

logger = logging.getLogger(__name__)

_NEWSAPI_BASE = "https://newsapi.org/v2/everything"
_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_MAX_TEXT_CHARS = 8_000
_REQUEST_TIMEOUT = 15


class NewsProducer:
    """Polls NewsAPI and GDELT for keyword-matching articles and publishes to Kafka."""

    def __init__(self) -> None:
        self._api_key = os.environ.get("NEWSAPI_KEY", "")
        self._keywords: list[str] = [
            k.strip()
            for k in os.environ.get("NEWS_KEYWORDS", "").split(",")
            if k.strip()
        ]
        if not self._keywords:
            logger.warning(
                "NEWS_KEYWORDS is not set — NewsProducer will publish nothing. "
                "Set it to a comma-separated list of search terms."
            )

        self._interval = int(os.environ.get("NEWS_POLL_INTERVAL", "300"))
        self._language = os.environ.get("NEWSAPI_LANGUAGE", "en")
        self._page_size = min(int(os.environ.get("NEWSAPI_PAGE_SIZE", "50")), 100)
        self._gdelt_enabled = os.environ.get("GDELT_ENABLED", "true").lower() != "false"
        self._gdelt_max = int(os.environ.get("GDELT_MAX_RECORDS", "25"))

        self._producer = create_producer()
        self._seen = SeenURLCache(prefix="news")
        logger.info(
            "NewsProducer ready — keywords=%s newsapi=%s gdelt=%s interval=%ds",
            self._keywords,
            bool(self._api_key),
            self._gdelt_enabled,
            self._interval,
        )

    def run(self) -> None:
        """Poll loop — runs indefinitely."""
        logger.info("NewsProducer starting")
        while True:
            published = 0
            for keyword in self._keywords:
                if self._api_key:
                    published += self._poll_newsapi(keyword)
                if self._gdelt_enabled:
                    published += self._poll_gdelt(keyword)
            logger.info("NewsProducer cycle — %d new event(s) published", published)
            time.sleep(self._interval)

    # ── NewsAPI ───────────────────────────────────────────────────────────────

    def _poll_newsapi(self, keyword: str) -> int:
        params: dict[str, Any] = {
            "q": keyword,
            "language": self._language,
            "pageSize": self._page_size,
            "sortBy": "publishedAt",
            "apiKey": self._api_key,
        }
        try:
            resp = requests.get(_NEWSAPI_BASE, params=params, timeout=_REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.error("NewsAPI request failed for %r: %s", keyword, exc)
            return 0

        if resp.status_code == 429:
            logger.warning("NewsAPI rate limit reached for %r — backing off", keyword)
            time.sleep(60)
            return 0
        if resp.status_code != 200:
            logger.error("NewsAPI returned %d for %r: %s", resp.status_code, keyword, resp.text[:200])
            return 0

        articles = resp.json().get("articles", [])
        return self._publish_articles(articles, source_hint="newsapi", keyword=keyword)

    # ── GDELT ─────────────────────────────────────────────────────────────────

    def _poll_gdelt(self, keyword: str) -> int:
        params: dict[str, Any] = {
            "query": keyword,
            "mode": "artlist",
            "maxrecords": self._gdelt_max,
            "format": "json",
            "sort": "datedesc",
        }
        try:
            resp = requests.get(_GDELT_BASE, params=params, timeout=_REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            logger.error("GDELT request failed for %r: %s", keyword, exc)
            return 0

        if resp.status_code != 200:
            logger.warning("GDELT returned %d for %r", resp.status_code, keyword)
            return 0

        try:
            data = resp.json()
        except ValueError as exc:
            logger.warning("GDELT response not valid JSON for %r: %s", keyword, exc)
            return 0

        articles = data.get("articles", [])
        return self._publish_articles(articles, source_hint="gdelt", keyword=keyword)

    # ── Shared ────────────────────────────────────────────────────────────────

    def _publish_articles(
        self, articles: list[dict], source_hint: str, keyword: str
    ) -> int:
        published = 0
        for article in articles:
            url = article.get("url") or article.get("url", "")
            if not url:
                continue
            if self._seen.is_seen(url):
                continue

            event = self._build_event(article, url, source_hint, keyword)
            publish_with_retry(
                self._producer,
                TOPIC_RAW,
                event.to_kafka_payload(),
                key=event.event_id,
            )
            self._seen.mark_seen(url)
            published += 1

        return published

    def _build_event(
        self, article: dict, url: str, source_hint: str, keyword: str
    ) -> RawEvent:
        title = article.get("title") or article.get("seendate") or ""
        description = article.get("description") or article.get("socialimage") or ""
        text = f"{title}\n{description}".strip()[:_MAX_TEXT_CHARS]

        # NewsAPI uses "publishedAt", GDELT uses "seendate" (YYYYMMDDTHHMMSSZ)
        collected_at = _parse_date(article.get("publishedAt") or article.get("seendate"))

        author = ""
        if article.get("author"):
            author = str(article["author"])
        elif article.get("source") and isinstance(article["source"], dict):
            author = article["source"].get("name", "")
        elif isinstance(article.get("source"), str):
            author = article["source"]

        return RawEvent(
            event_id=make_event_id("news", url),
            source="news",
            collected_at=collected_at,
            raw_text=text,
            url=url,
            author=author,
            engagement_score=0.0,
            metadata={
                "news_source": source_hint,
                "search_keyword": keyword,
                "title": title,
            },
        )


def _parse_date(value: str | None) -> datetime:
    """Parse ISO 8601 or GDELT date string; fall back to utcnow on failure."""
    if not value:
        return datetime.now(tz=timezone.utc)
    try:
        # GDELT format: 20260429T120000Z
        if len(value) == 16 and "T" in value and value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            return dt.replace(tzinfo=timezone.utc)
        # ISO 8601 (NewsAPI)
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(tz=timezone.utc)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    NewsProducer().run()
