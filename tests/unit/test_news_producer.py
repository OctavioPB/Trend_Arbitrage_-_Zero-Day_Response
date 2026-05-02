"""Unit tests for ingestion producers and the F3 source-weight integration.

Covers:
  - Schema validation: output RawEvent has correct source, required fields
  - Deduplication: same URL produces same event_id (UUID5); is_seen/mark_seen
  - NewsProducer: NewsAPI articles, GDELT articles, date parsing, dedup skip
  - RSSProducer: well-formed entries, malformed XML (bozo), missing URL skip
  - LinkedInProducer: post extraction, rate-limit back-off, missing API key
  - Source weight integration: load_source_weights + weighted _compute_volume
  - MPIResult includes source_weights field
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.models import RawEvent, make_event_id


# ── Helpers ───────────────────────────────────────────────────────────────────


def _minimal_event(**overrides) -> dict:
    base = dict(
        event_id="test-id",
        source="news",
        collected_at=datetime.now(tz=timezone.utc),
        raw_text="headline about AI chips",
        url="https://example.com/article/1",
        author="TechDesk",
        engagement_score=0.0,
    )
    base.update(overrides)
    return base


# ── RawEvent schema ───────────────────────────────────────────────────────────


class TestRawEventSchema:
    def test_news_source_is_valid(self):
        ev = RawEvent(**_minimal_event(source="news"))
        assert ev.source == "news"

    def test_linkedin_source_is_valid(self):
        ev = RawEvent(**_minimal_event(source="linkedin"))
        assert ev.source == "linkedin"

    def test_rss_source_is_valid(self):
        ev = RawEvent(**_minimal_event(source="rss"))
        assert ev.source == "rss"

    def test_unknown_source_raises(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RawEvent(**_minimal_event(source="snapchat"))

    def test_to_kafka_payload_returns_dict(self):
        ev = RawEvent(**_minimal_event())
        payload = ev.to_kafka_payload()
        assert isinstance(payload, dict)
        assert payload["source"] == "news"
        assert "event_id" in payload
        assert "collected_at" in payload

    def test_to_kafka_payload_is_json_serializable(self):
        ev = RawEvent(**_minimal_event())
        payload = ev.to_kafka_payload()
        json.dumps(payload)  # must not raise


# ── Deduplication ─────────────────────────────────────────────────────────────


class TestMakeEventId:
    def test_same_url_same_id(self):
        id1 = make_event_id("news", "https://example.com/article/1")
        id2 = make_event_id("news", "https://example.com/article/1")
        assert id1 == id2

    def test_different_url_different_id(self):
        id1 = make_event_id("news", "https://example.com/article/1")
        id2 = make_event_id("news", "https://example.com/article/2")
        assert id1 != id2

    def test_different_source_different_id(self):
        id1 = make_event_id("news", "https://example.com/article/1")
        id2 = make_event_id("rss", "https://example.com/article/1")
        assert id1 != id2

    def test_returns_valid_uuid_string(self):
        import uuid

        result = make_event_id("news", "https://example.com")
        uuid.UUID(result)  # must not raise


class TestSeenURLCache:
    def test_is_seen_false_initially(self):
        from ingestion.dedup import SeenURLCache

        cache = SeenURLCache(prefix="test_fresh")
        assert not cache.is_seen("https://example.com/new-article")

    def test_is_seen_true_after_mark(self):
        from ingestion.dedup import SeenURLCache

        cache = SeenURLCache(prefix="test_mark")
        url = "https://example.com/marked-article"
        cache.mark_seen(url)
        assert cache.is_seen(url)

    def test_different_urls_are_independent(self):
        from ingestion.dedup import SeenURLCache

        cache = SeenURLCache(prefix="test_indep")
        cache.mark_seen("https://example.com/a")
        assert not cache.is_seen("https://example.com/b")

    def test_works_without_redis(self):
        from ingestion.dedup import SeenURLCache

        with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
            cache = SeenURLCache(prefix="test_no_redis")
        url = "https://example.com/no-redis"
        assert not cache.is_seen(url)
        cache.mark_seen(url)
        assert cache.is_seen(url)

    def test_falls_back_to_memory_on_redis_error(self):
        from ingestion.dedup import SeenURLCache

        cache = SeenURLCache(prefix="test_redis_err")
        # Force Redis to be None (simulating connection failure)
        cache._redis = None
        url = "https://example.com/redis-fail"
        cache.mark_seen(url)
        assert cache.is_seen(url)


# ── NewsProducer ──────────────────────────────────────────────────────────────


class TestNewsProducerBuildEvent:
    def _producer(self):
        from ingestion.producers.news_producer import NewsProducer

        with patch("ingestion.producers.news_producer.create_producer", return_value=MagicMock()):
            with patch.dict("os.environ", {
                "NEWSAPI_KEY": "test-key",
                "NEWS_KEYWORDS": "ai chips",
                "REDIS_URL": "",
            }):
                p = NewsProducer()
                p._seen._redis = None
                return p

    def test_build_event_news_source(self):
        p = self._producer()
        article = {
            "url": "https://techcrunch.com/ai-chips",
            "title": "AI chip shortage",
            "description": "Demand surges",
            "publishedAt": "2026-05-01T10:00:00Z",
            "author": "TC Writer",
        }
        event = p._build_event(article, article["url"], "newsapi", "ai chips")
        assert event.source == "news"
        assert event.url == "https://techcrunch.com/ai-chips"
        assert event.author == "TC Writer"
        assert "AI chip shortage" in event.raw_text

    def test_build_event_gdelt_date_format(self):
        p = self._producer()
        article = {
            "url": "https://news.example.com/gdelt",
            "title": "GDELT article",
            "seendate": "20260501T120000Z",
        }
        event = p._build_event(article, article["url"], "gdelt", "ai chips")
        assert event.collected_at.year == 2026
        assert event.collected_at.month == 5
        assert event.collected_at.day == 1

    def test_build_event_missing_date_falls_back_to_now(self):
        p = self._producer()
        article = {"url": "https://example.com/no-date", "title": "No date"}
        event = p._build_event(article, article["url"], "newsapi", "kw")
        assert event.collected_at.tzinfo is not None

    def test_build_event_source_name_from_dict(self):
        p = self._producer()
        article = {
            "url": "https://example.com/source-dict",
            "title": "T",
            "source": {"id": "bbc-news", "name": "BBC News"},
        }
        event = p._build_event(article, article["url"], "newsapi", "kw")
        assert event.author == "BBC News"

    def test_dedup_skips_seen_url(self):
        p = self._producer()
        url = "https://example.com/seen"
        p._seen.mark_seen(url)

        articles = [{"url": url, "title": "T"}]
        with patch.object(p, "_producer") as mock_prod:
            count = p._publish_articles(articles, source_hint="newsapi", keyword="kw")

        assert count == 0

    @patch("ingestion.producers.news_producer.requests.get")
    def test_poll_newsapi_handles_rate_limit(self, mock_get):
        p = self._producer()
        mock_get.return_value.status_code = 429
        count = p._poll_newsapi("ai chips")
        assert count == 0

    @patch("ingestion.producers.news_producer.requests.get")
    def test_poll_newsapi_handles_request_exception(self, mock_get):
        import requests as req

        p = self._producer()
        mock_get.side_effect = req.ConnectionError("timeout")
        count = p._poll_newsapi("ai chips")
        assert count == 0

    @patch("ingestion.producers.news_producer.requests.get")
    def test_poll_gdelt_handles_invalid_json(self, mock_get):
        p = self._producer()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("not json")
        mock_get.return_value = mock_resp
        count = p._poll_gdelt("ai chips")
        assert count == 0


# ── RSSProducer ───────────────────────────────────────────────────────────────


class TestRSSProducerPollFeed:
    def _producer(self):
        from ingestion.producers.rss_producer import RSSProducer

        with patch("ingestion.producers.rss_producer.create_producer", return_value=MagicMock()):
            with patch.dict("os.environ", {"REDIS_URL": ""}):
                p = RSSProducer.__new__(RSSProducer)
                p._interval = 900
                p._producer = MagicMock()
                p._seen = __import__("ingestion.dedup", fromlist=["SeenURLCache"]).SeenURLCache(prefix="rss_test")
                p._seen._redis = None
                return p

    def _make_feed(self, entries: list[dict], bozo: bool = False) -> object:
        """Build a minimal feedparser-like result."""
        result = MagicMock()
        result.get.side_effect = lambda key, default=None: {
            "bozo": bozo,
            "bozo_exception": Exception("bad xml") if bozo else None,
        }.get(key, default)
        result.entries = [_make_feedparser_entry(e) for e in entries]
        return result

    @patch("ingestion.producers.rss_producer.publish_with_retry")
    @patch("ingestion.producers.rss_producer.feedparser.parse")
    def test_publishes_new_entries(self, mock_parse, mock_publish):
        p = self._producer()
        mock_parse.return_value = self._make_feed([
            {"link": "https://tc.com/1", "title": "Post 1"},
            {"link": "https://tc.com/2", "title": "Post 2"},
        ])
        count = p._poll_feed({"url": "https://tc.com/feed/", "label": "tc"})
        assert count == 2
        assert mock_publish.call_count == 2

    @patch("ingestion.producers.rss_producer.feedparser.parse")
    def test_skips_malformed_feed(self, mock_parse):
        p = self._producer()
        mock_parse.return_value = self._make_feed([], bozo=True)
        count = p._poll_feed({"url": "https://bad.com/feed/", "label": "bad"})
        assert count == 0

    @patch("ingestion.producers.rss_producer.publish_with_retry")
    @patch("ingestion.producers.rss_producer.feedparser.parse")
    def test_skips_entry_without_url(self, mock_parse, mock_publish):
        p = self._producer()
        mock_parse.return_value = self._make_feed([{"link": "", "title": "No URL"}])
        count = p._poll_feed({"url": "https://tc.com/feed/", "label": "tc"})
        assert count == 0
        mock_publish.assert_not_called()

    @patch("ingestion.producers.rss_producer.publish_with_retry")
    @patch("ingestion.producers.rss_producer.feedparser.parse")
    def test_dedup_skips_seen_url(self, mock_parse, mock_publish):
        p = self._producer()
        url = "https://tc.com/seen"
        p._seen.mark_seen(url)
        mock_parse.return_value = self._make_feed([{"link": url, "title": "Seen"}])
        count = p._poll_feed({"url": "https://tc.com/feed/", "label": "tc"})
        assert count == 0
        mock_publish.assert_not_called()

    @patch("ingestion.producers.rss_producer.publish_with_retry")
    @patch("ingestion.producers.rss_producer.feedparser.parse")
    def test_build_event_has_rss_source(self, mock_parse, mock_publish):
        p = self._producer()
        mock_parse.return_value = self._make_feed([
            {"link": "https://tc.com/new-post", "title": "AI News"}
        ])
        with patch.object(p, "_build_event", wraps=p._build_event) as mock_build:
            p._poll_feed({"url": "https://tc.com/feed/", "label": "tc"})
            event = mock_build.return_value
        # Verify via the actual publish call payload
        payload = mock_publish.call_args[0][2]
        assert payload["source"] == "rss"


def _make_feedparser_entry(data: dict) -> object:
    entry = MagicMock()
    entry.link = data.get("link", "")
    entry.title = data.get("title", "")
    entry.summary = data.get("summary", "")
    entry.author = data.get("author", "")
    entry.published_parsed = None
    return entry


# ── LinkedInProducer ──────────────────────────────────────────────────────────


class TestLinkedInProducerExtractPosts:
    def _producer(self):
        from ingestion.producers.linkedin_producer import LinkedInProducer

        with patch("ingestion.producers.linkedin_producer.create_producer", return_value=MagicMock()):
            with patch.dict("os.environ", {
                "RAPIDAPI_KEY": "test-key",
                "LINKEDIN_COMPANY_HANDLES": "openai,anthropic",
                "REDIS_URL": "",
            }):
                p = LinkedInProducer()
                p._seen._redis = None
                return p

    def test_extract_posts_from_list(self):
        p = self._producer()
        posts = p._extract_posts([{"id": "1"}, {"id": "2"}])
        assert len(posts) == 2

    def test_extract_posts_from_updates_key(self):
        p = self._producer()
        posts = p._extract_posts({"updates": [{"id": "a"}, {"id": "b"}]})
        assert len(posts) == 2

    def test_extract_posts_empty_unknown_structure(self):
        p = self._producer()
        posts = p._extract_posts({"unexpected": "structure"})
        assert posts == []

    def test_extract_url_from_postUrl_key(self):
        p = self._producer()
        url = p._extract_url({"postUrl": "https://linkedin.com/post/123"}, "openai")
        assert url == "https://linkedin.com/post/123"

    def test_extract_url_fallback_from_id(self):
        p = self._producer()
        url = p._extract_url({"id": "urn:li:activity:123"}, "openai")
        assert "urn:li:activity:123" in url

    def test_extract_url_empty_when_no_identifier(self):
        p = self._producer()
        url = p._extract_url({}, "openai")
        assert url == ""

    def test_build_event_linkedin_source(self):
        p = self._producer()
        post = {
            "postUrl": "https://linkedin.com/post/999",
            "text": "Exciting news about AI",
            "createdAt": 1746057600000,  # Unix ms
            "likeCount": 42,
            "commentCount": 5,
        }
        event = p._build_event(post, post["postUrl"], "openai")
        assert event.source == "linkedin"
        assert event.engagement_score == pytest.approx(47.0)
        assert event.metadata["company_handle"] == "openai"

    @patch("ingestion.producers.linkedin_producer.requests.get")
    def test_poll_handle_rate_limit_sets_cooldown(self, mock_get):
        import time

        p = self._producer()
        mock_get.return_value.status_code = 429
        count = p._poll_handle("openai")
        assert count == 0
        assert p._rate_limited_until.get("openai", 0) > time.monotonic()

    @patch("ingestion.producers.linkedin_producer.requests.get")
    def test_poll_handle_skips_during_cooldown(self, mock_get):
        import time

        p = self._producer()
        p._rate_limited_until["openai"] = time.monotonic() + 9999
        count = p._poll_handle("openai")
        assert count == 0
        mock_get.assert_not_called()


# ── Source weights in MPI calculator ─────────────────────────────────────────


class TestSourceWeightsInMPI:
    def test_load_source_weights_from_file(self, tmp_path):
        from predictive.mpi_calculator import load_source_weights

        weights_file = tmp_path / "sw.json"
        weights_file.write_text(
            json.dumps({"reddit": 1.0, "news": 1.2, "linkedin": 1.1, "_comment": "x"})
        )
        with patch("predictive.mpi_calculator._SOURCE_WEIGHTS_PATH", weights_file):
            weights = load_source_weights()

        assert weights["reddit"] == pytest.approx(1.0)
        assert weights["news"] == pytest.approx(1.2)
        assert weights["linkedin"] == pytest.approx(1.1)
        assert "_comment" not in weights

    def test_load_source_weights_missing_file_returns_empty(self, tmp_path):
        from predictive.mpi_calculator import load_source_weights

        with patch(
            "predictive.mpi_calculator._SOURCE_WEIGHTS_PATH",
            tmp_path / "nonexistent.json",
        ):
            weights = load_source_weights()

        assert weights == {}

    def test_compute_volume_uses_weighted_sum(self):
        from predictive.mpi_calculator import _compute_volume

        signals = [
            {"source": "news"},     # weight 1.2
            {"source": "reddit"},   # weight 1.0
            {"source": "linkedin"}, # weight 1.1
        ]
        sw = {"reddit": 1.0, "news": 1.2, "linkedin": 1.1}
        baseline = 3.3  # sum of weights = 3.3 → score should be 1.0
        score, weighted = _compute_volume(signals, baseline, sw)

        assert weighted == pytest.approx(3.3)
        assert score == pytest.approx(1.0)

    def test_compute_volume_unknown_source_defaults_to_1(self):
        from predictive.mpi_calculator import _compute_volume

        signals = [{"source": "pagerduty"}]  # not in weights
        score, weighted = _compute_volume(signals, baseline=1.0, source_weights={})
        assert weighted == pytest.approx(1.0)

    def test_compute_volume_high_weight_raises_score(self):
        from predictive.mpi_calculator import _compute_volume

        news_signals = [{"source": "news"}, {"source": "news"}]  # 2 × 1.2 = 2.4
        rss_signals = [{"source": "rss"}, {"source": "rss"}]    # 2 × 0.7 = 1.4
        sw = {"news": 1.2, "rss": 0.7}

        news_score, _ = _compute_volume(news_signals, baseline=2.0, source_weights=sw)
        rss_score, _ = _compute_volume(rss_signals, baseline=2.0, source_weights=sw)

        assert news_score > rss_score

    def test_calculate_mpi_result_includes_source_weights(self):
        from datetime import timezone

        from predictive.mpi_calculator import calculate_mpi

        signals = [
            {
                "source": "news",
                "collected_at": datetime.now(tz=timezone.utc),
                "sentiment": "positive",
            }
        ]
        result = calculate_mpi(
            signals=signals,
            source_weights={"news": 1.2},
            weights={"volume": 0.4, "velocity": 0.35, "sentiment": 0.25},
        )
        assert "news" in result.source_weights
        assert result.weighted_signal_count == pytest.approx(1.2)

    def test_changing_source_weight_changes_mpi(self):
        from predictive.mpi_calculator import calculate_mpi

        _NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        signals = [{"source": "news", "collected_at": _NOW, "sentiment": "positive"}]
        weights = {"volume": 0.4, "velocity": 0.35, "sentiment": 0.25}

        low = calculate_mpi(signals=signals, weights=weights, source_weights={"news": 0.5}, now=_NOW)
        high = calculate_mpi(signals=signals, weights=weights, source_weights={"news": 2.0}, now=_NOW)

        assert high.mpi_score > low.mpi_score
