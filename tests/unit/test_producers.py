"""Unit tests for ingestion producers.

All tests mock KafkaProducer and external API clients — no running services needed.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from kafka.errors import KafkaError
from pydantic import ValidationError

from ingestion.config.kafka_config import publish_with_retry
from ingestion.models import RawEvent, make_event_id
from ingestion.producers.reddit_producer import RedditProducer
from ingestion.producers.scraper_producer import ScraperProducer


# ── RawEvent model ────────────────────────────────────────────────────────────


class TestRawEvent:
    def _valid_kwargs(self) -> dict[str, Any]:
        return {
            "event_id": str(uuid.uuid4()),
            "source": "reddit",
            "collected_at": datetime.now(tz=timezone.utc),
            "raw_text": "Some trending topic discussion",
            "url": "https://reddit.com/r/technology/comments/abc/test",
            "author": "testuser",
            "engagement_score": 1234.0,
            "metadata": {"post_id": "abc", "subreddit": "technology"},
        }

    def test_all_required_fields_accepted(self) -> None:
        event = RawEvent(**self._valid_kwargs())
        assert event.event_id
        assert event.source == "reddit"
        assert event.raw_text

    def test_source_must_be_valid_literal(self) -> None:
        kwargs = self._valid_kwargs()
        kwargs["source"] = "instagram"
        with pytest.raises(ValidationError):
            RawEvent(**kwargs)

    def test_metadata_defaults_to_empty_dict(self) -> None:
        kwargs = self._valid_kwargs()
        del kwargs["metadata"]
        event = RawEvent(**kwargs)
        assert event.metadata == {}

    def test_to_kafka_payload_is_json_serializable(self) -> None:
        event = RawEvent(**self._valid_kwargs())
        payload = event.to_kafka_payload()
        dumped = json.dumps(payload)
        assert isinstance(dumped, str)

    def test_to_kafka_payload_collected_at_is_string(self) -> None:
        event = RawEvent(**self._valid_kwargs())
        payload = event.to_kafka_payload()
        assert isinstance(payload["collected_at"], str)

    def test_no_secrets_in_kafka_payload(self) -> None:
        """Payload must not contain any API key patterns."""
        kwargs = self._valid_kwargs()
        kwargs["raw_text"] = "Normal post content without secrets"
        event = RawEvent(**kwargs)
        payload_str = json.dumps(event.to_kafka_payload())
        assert "sk-ant-" not in payload_str
        assert "Bearer " not in payload_str
        assert "REDDIT_CLIENT_SECRET" not in payload_str


# ── make_event_id ─────────────────────────────────────────────────────────────


class TestMakeEventId:
    def test_is_deterministic(self) -> None:
        """Same source + content_key always produces the same ID."""
        assert make_event_id("reddit", "abc123") == make_event_id("reddit", "abc123")

    def test_differs_across_sources(self) -> None:
        """Same content_key on different sources gives different IDs."""
        assert make_event_id("reddit", "abc123") != make_event_id("twitter", "abc123")

    def test_differs_across_content_keys(self) -> None:
        """Different content keys give different IDs."""
        assert make_event_id("reddit", "abc123") != make_event_id("reddit", "def456")

    def test_output_is_valid_uuid_format(self) -> None:
        """Returned string is a parseable UUID."""
        result = make_event_id("scraper", "https://example.com:abcdef01")
        parsed = uuid.UUID(result)
        assert parsed.version == 5


# ── publish_with_retry ────────────────────────────────────────────────────────


class TestPublishWithRetry:
    def _make_mock_producer(self) -> MagicMock:
        producer = MagicMock()
        future = MagicMock()
        future.get.return_value = None
        producer.send.return_value = future
        return producer

    def test_publishes_successfully_on_first_try(self) -> None:
        producer = self._make_mock_producer()
        publish_with_retry(producer, "raw_signals", {"event_id": "x"})
        producer.send.assert_called_once_with(
            "raw_signals", value={"event_id": "x"}, key=None
        )

    def test_publishes_with_key(self) -> None:
        producer = self._make_mock_producer()
        publish_with_retry(producer, "raw_signals", {"event_id": "x"}, key="x")
        _, kwargs = producer.send.call_args
        assert kwargs["key"] == b"x"

    def test_retries_on_kafka_error(self) -> None:
        """publish_with_retry should retry and succeed on the second attempt."""
        producer = MagicMock()
        fail_future = MagicMock()
        fail_future.get.side_effect = KafkaError("broker unavailable")
        ok_future = MagicMock()
        ok_future.get.return_value = None
        producer.send.side_effect = [
            KafkaError("connection refused"),
            ok_future,
        ]

        publish_with_retry(producer, "raw_signals", {"event_id": "y"})
        assert producer.send.call_count == 2

    def test_reraises_after_max_retries(self) -> None:
        """After all retries are exhausted, the KafkaError propagates."""
        producer = MagicMock()
        producer.send.side_effect = KafkaError("permanent failure")

        with pytest.raises(KafkaError):
            publish_with_retry(producer, "raw_signals", {"event_id": "z"})


# ── RedditProducer._build_event ───────────────────────────────────────────────


class TestRedditProducerBuildEvent:
    def _make_producer(self) -> RedditProducer:
        """Instantiate RedditProducer without connecting to Reddit or Kafka."""
        with (
            patch("ingestion.producers.reddit_producer.praw.Reddit"),
            patch("ingestion.producers.reddit_producer.create_producer"),
            patch.dict(
                "os.environ",
                {
                    "REDDIT_CLIENT_ID": "fake_id",
                    "REDDIT_CLIENT_SECRET": "fake_secret",
                },
            ),
        ):
            return RedditProducer()

    def _mock_submission(
        self,
        post_id: str = "abc123",
        title: str = "Test post",
        selftext: str = "Body text",
        score: int = 500,
        upvote_ratio: float = 0.9,
        num_comments: int = 42,
        permalink: str = "/r/technology/comments/abc123/test",
        author: str = "user1",
        flair: str | None = None,
    ) -> MagicMock:
        sub = MagicMock()
        sub.id = post_id
        sub.title = title
        sub.selftext = selftext
        sub.score = score
        sub.upvote_ratio = upvote_ratio
        sub.num_comments = num_comments
        sub.permalink = permalink
        sub.author = author
        sub.link_flair_text = flair
        return sub

    def test_event_id_is_deterministic(self) -> None:
        producer = self._make_producer()
        sub = self._mock_submission(post_id="abc123")
        event1 = producer._build_event(sub, "technology")
        event2 = producer._build_event(sub, "technology")
        assert event1.event_id == event2.event_id

    def test_event_id_differs_across_posts(self) -> None:
        producer = self._make_producer()
        sub1 = self._mock_submission(post_id="abc123")
        sub2 = self._mock_submission(post_id="def456")
        assert producer._build_event(sub1, "technology").event_id != producer._build_event(
            sub2, "technology"
        ).event_id

    def test_source_is_reddit(self) -> None:
        producer = self._make_producer()
        event = producer._build_event(self._mock_submission(), "technology")
        assert event.source == "reddit"

    def test_raw_text_combines_title_and_body(self) -> None:
        producer = self._make_producer()
        sub = self._mock_submission(title="Headline", selftext="Body paragraph")
        event = producer._build_event(sub, "technology")
        assert "Headline" in event.raw_text
        assert "Body paragraph" in event.raw_text

    def test_raw_text_title_only_when_no_body(self) -> None:
        producer = self._make_producer()
        sub = self._mock_submission(title="Only a title", selftext="")
        event = producer._build_event(sub, "technology")
        assert event.raw_text == "Only a title"

    def test_engagement_score_is_float(self) -> None:
        producer = self._make_producer()
        event = producer._build_event(self._mock_submission(score=1234), "technology")
        assert isinstance(event.engagement_score, float)
        assert event.engagement_score == 1234.0

    def test_deleted_author_handled(self) -> None:
        producer = self._make_producer()
        sub = self._mock_submission()
        sub.author = None
        event = producer._build_event(sub, "technology")
        assert event.author == "[deleted]"

    def test_metadata_contains_required_keys(self) -> None:
        producer = self._make_producer()
        event = producer._build_event(self._mock_submission(), "technology")
        for key in ("post_id", "subreddit", "upvote_ratio", "num_comments"):
            assert key in event.metadata

    def test_schema_validates_against_raw_event(self) -> None:
        """Ensure the built dict round-trips through RawEvent without errors."""
        producer = self._make_producer()
        event = producer._build_event(self._mock_submission(), "technology")
        payload = event.to_kafka_payload()
        restored = RawEvent.model_validate(payload)
        assert restored.event_id == event.event_id


# ── ScraperProducer._robots_allows ────────────────────────────────────────────


class TestScraperRobotsAllows:
    def _make_scraper(self) -> ScraperProducer:
        with (
            patch("ingestion.producers.scraper_producer.create_producer"),
            patch("ingestion.producers.scraper_producer._TARGETS_PATH") as mock_path,
        ):
            mock_path.exists.return_value = False
            return ScraperProducer()

    def test_allows_when_robots_txt_unreachable(self) -> None:
        scraper = self._make_scraper()
        with patch("urllib.robotparser.RobotFileParser.read", side_effect=OSError("timeout")):
            assert scraper._robots_allows("https://example.com/page") is True

    def test_caches_parser_per_domain(self) -> None:
        scraper = self._make_scraper()
        with patch("urllib.robotparser.RobotFileParser.read"):
            with patch("urllib.robotparser.RobotFileParser.can_fetch", return_value=True):
                scraper._robots_allows("https://example.com/page1")
                scraper._robots_allows("https://example.com/page2")
        assert "https://example.com" in scraper._robots_cache
        assert len(scraper._robots_cache) == 1
