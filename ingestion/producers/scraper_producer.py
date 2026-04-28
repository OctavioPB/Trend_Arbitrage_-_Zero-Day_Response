"""Scraper producer — headless Playwright crawl of configured URLs, publishes to Kafka."""

import asyncio
import hashlib
import json
import logging
import os
import random
import urllib.parse
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Browser, async_playwright

from ingestion.config.kafka_config import TOPIC_RAW, create_producer, publish_with_retry
from ingestion.models import RawEvent, make_event_id

logger = logging.getLogger(__name__)

_USER_AGENT = "trend-arbitrage/1.0 (+https://github.com/opb/trend-arbitrage)"
_MAX_TEXT_CHARS = 10_000
_TARGETS_PATH = Path("config/scraper_targets.json")


class ScraperProducer:
    """Iterates over target URLs, scrapes visible text, and publishes raw events."""

    def __init__(self) -> None:
        self._targets: list[str] = self._load_targets()
        self._interval: int = int(os.environ.get("SCRAPER_INTERVAL", "600"))
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._producer = create_producer()
        logger.info(
            "ScraperProducer ready — %d target(s), interval=%ds",
            len(self._targets),
            self._interval,
        )

    def run(self) -> None:
        """Entry point — runs the async scrape loop in the current thread."""
        asyncio.run(self._loop())

    # ── private ──────────────────────────────────────────────────────────────

    def _load_targets(self) -> list[str]:
        if not _TARGETS_PATH.exists():
            logger.warning(
                "%s not found — scraper will do nothing. "
                "Add target URLs there to enable crawling.",
                _TARGETS_PATH,
            )
            return []
        with _TARGETS_PATH.open() as fh:
            targets = json.load(fh)
        if not isinstance(targets, list):
            logger.error("%s must be a JSON array of URL strings", _TARGETS_PATH)
            return []
        return [str(u) for u in targets if u]

    async def _loop(self) -> None:
        while True:
            if not self._targets:
                logger.warning("No targets configured — sleeping %ds", self._interval)
                await asyncio.sleep(self._interval)
                continue

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                for url in self._targets:
                    try:
                        await self._scrape_one(browser, url)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Scrape failed for %s: %s", url, exc)
                    delay = random.uniform(3, 8)
                    await asyncio.sleep(delay)
                await browser.close()

            await asyncio.sleep(self._interval)

    async def _scrape_one(self, browser: Browser, url: str) -> None:
        if not await asyncio.to_thread(self._robots_allows, url):
            logger.info("robots.txt disallows %s — skipping", url)
            return

        page = await browser.new_page(user_agent=_USER_AGENT)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            text: str = await page.evaluate("() => document.body.innerText")
            title: str = await page.title()
        finally:
            await page.close()

        text = text.strip()[:_MAX_TEXT_CHARS]
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        event = RawEvent(
            event_id=make_event_id("scraper", f"{url}:{content_hash}"),
            source="scraper",
            collected_at=datetime.now(tz=timezone.utc),
            raw_text=text,
            url=url,
            author="",
            engagement_score=0.0,
            metadata={
                "page_title": title,
                "content_hash": content_hash,
                "scrape_url": url,
            },
        )
        publish_with_retry(
            self._producer,
            TOPIC_RAW,
            event.to_kafka_payload(),
            key=event.event_id,
        )
        logger.info("Published scraped event from %s (hash=%s)", url, content_hash)

    def _robots_allows(self, url: str) -> bool:
        """Check robots.txt for the given URL. Caches parsers per domain."""
        parsed = urllib.parse.urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain not in self._robots_cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{domain}/robots.txt")
            try:
                rp.read()
            except Exception as exc:
                logger.debug("Could not fetch robots.txt for %s: %s — assuming allowed", domain, exc)
                rp.allow_all = True
            self._robots_cache[domain] = rp

        return self._robots_cache[domain].can_fetch(_USER_AGENT, url)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    ScraperProducer().run()
