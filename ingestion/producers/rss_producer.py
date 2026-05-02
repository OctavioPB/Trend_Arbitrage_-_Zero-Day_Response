"""RSS/Atom producer — polls feeds in config/rss_feeds.json and publishes raw events.

Deduplication:
    URL hash via SeenURLCache (Redis-backed, 24-hour TTL).
    Same URL across two poll cycles is silently skipped.

Error handling:
    Malformed XML (feedparser bozo=True) is logged and skipped; the producer
    continues with remaining feeds. A single bad feed never crashes the loop.

Config via environment:
    RSS_POLL_INTERVAL  seconds between full sweep of all feeds (default 900)
    SOURCE_WEIGHTS_PATH  path to source_weights.json (default config/source_weights.json)
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser

from ingestion.config.kafka_config import TOPIC_RAW, create_producer, publish_with_retry
from ingestion.dedup import SeenURLCache
from ingestion.models import RawEvent, make_event_id

logger = logging.getLogger(__name__)

_FEEDS_PATH = Path(os.environ.get("RSS_FEEDS_PATH", "config/rss_feeds.json"))
_MAX_TEXT_CHARS = 8_000


class RSSProducer:
    """Polls every feed in config/rss_feeds.json and publishes new entries to Kafka."""

    def __init__(self) -> None:
        self._feeds = self._load_feeds()
        self._interval = int(os.environ.get("RSS_POLL_INTERVAL", "900"))
        self._producer = create_producer()
        self._seen = SeenURLCache(prefix="rss")
        logger.info(
            "RSSProducer ready — %d feed(s), interval=%ds",
            len(self._feeds),
            self._interval,
        )

    def run(self) -> None:
        """Poll all feeds in a loop. Never raises."""
        logger.info("RSSProducer starting")
        while True:
            published = 0
            for feed_cfg in self._feeds:
                try:
                    published += self._poll_feed(feed_cfg)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Unexpected error polling feed %s: %s",
                        feed_cfg.get("label", feed_cfg.get("url")),
                        exc,
                    )
            logger.info("RSSProducer cycle complete — %d new event(s) published", published)
            time.sleep(self._interval)

    # ── Private ───────────────────────────────────────────────────────────────

    def _load_feeds(self) -> list[dict]:
        import json

        if not _FEEDS_PATH.exists():
            logger.warning(
                "%s not found — RSS producer will do nothing. "
                "Create the file with a 'feeds' array to enable.",
                _FEEDS_PATH,
            )
            return []
        try:
            data = json.loads(_FEEDS_PATH.read_text(encoding="utf-8"))
            feeds = data.get("feeds", []) if isinstance(data, dict) else data
            valid = [f for f in feeds if isinstance(f, dict) and f.get("url")]
            logger.info("Loaded %d RSS feed(s) from %s", len(valid), _FEEDS_PATH)
            return valid
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load %s: %s", _FEEDS_PATH, exc)
            return []

    def _poll_feed(self, feed_cfg: dict) -> int:
        url: str = feed_cfg["url"]
        label: str = feed_cfg.get("label", url)
        category: str = feed_cfg.get("category", "")

        parsed = feedparser.parse(url)

        if parsed.get("bozo") and parsed.get("bozo_exception"):
            exc = parsed["bozo_exception"]
            logger.warning("Malformed feed %s (%s): %s — skipping", label, url, exc)
            return 0

        published = 0
        for entry in parsed.entries:
            entry_url = getattr(entry, "link", "") or ""
            if not entry_url:
                continue
            if self._seen.is_seen(entry_url):
                continue

            event = self._build_event(entry, entry_url, label, category)
            publish_with_retry(
                self._producer,
                TOPIC_RAW,
                event.to_kafka_payload(),
                key=event.event_id,
            )
            self._seen.mark_seen(entry_url)
            published += 1

        logger.debug("Feed %s: %d new entry/entries published", label, published)
        return published

    def _build_event(
        self,
        entry: object,
        url: str,
        label: str,
        category: str,
    ) -> RawEvent:
        title = getattr(entry, "title", "") or ""
        summary = getattr(entry, "summary", "") or ""
        text = f"{title}\n{summary}".strip()[:_MAX_TEXT_CHARS]

        author = ""
        if hasattr(entry, "author"):
            author = str(entry.author)
        elif hasattr(entry, "authors") and entry.authors:
            author = entry.authors[0].get("name", "")

        published_parsed = getattr(entry, "published_parsed", None)
        if published_parsed:
            import calendar

            collected_at = datetime.fromtimestamp(
                calendar.timegm(published_parsed), tz=timezone.utc
            )
        else:
            collected_at = datetime.now(tz=timezone.utc)

        return RawEvent(
            event_id=make_event_id("rss", url),
            source="rss",
            collected_at=collected_at,
            raw_text=text,
            url=url,
            author=author,
            engagement_score=0.0,
            metadata={
                "feed_label": label,
                "feed_category": category,
                "title": title,
            },
        )


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    RSSProducer().run()
