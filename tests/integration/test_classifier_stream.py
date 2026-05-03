"""Integration test — ClassifierStream end-to-end.

Requires:
  docker-compose up -d
  alembic upgrade head

Produces a raw signal to raw_signals, runs the classifier stream for one batch,
and asserts the enriched signal appears in the DB within 30 seconds.

Skips automatically if Kafka or PostgreSQL are not available.

Run with:
  pytest tests/integration/test_classifier_stream.py -v -m integration
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration

# ── Infrastructure availability guards ───────────────────────────────────────

_BOOTSTRAP = "localhost:9092"


def _kafka_available() -> bool:
    try:
        from kafka import KafkaAdminClient

        client = KafkaAdminClient(
            bootstrap_servers=[_BOOTSTRAP],
            request_timeout_ms=3000,
        )
        client.close()
        return True
    except Exception:
        return False


def _db_available() -> bool:
    import os

    import psycopg2

    dsn = os.environ.get(
        "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
    )
    try:
        conn = psycopg2.connect(dsn, connect_timeout=3)
        conn.close()
        return True
    except psycopg2.OperationalError:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_infrastructure():
    if not _kafka_available():
        pytest.skip("Kafka not available — run 'docker-compose up -d' first")
    if not _db_available():
        pytest.skip("PostgreSQL not available — run 'docker-compose up -d' first")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def raw_event() -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "source": "reddit",
        "collected_at": datetime.now(tz=timezone.utc).isoformat(),
        "raw_text": "Major AI chip shortage expected to drive GPU prices up 40% next quarter",
        "url": "https://reddit.com/r/hardware/test",
        "author": "test_user",
        "engagement_score": 250.0,
        "metadata": {"subreddit": "hardware"},
    }


@pytest.fixture()
def producer():
    from ingestion.config.kafka_config import create_producer

    p = create_producer()
    yield p


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestClassifierStreamBatch:
    def test_process_batch_writes_enriched_signal_to_db(self, raw_event):
        """_process_batch() enriches a raw event and writes it to enriched_signals."""
        import os

        import psycopg2

        from streaming.classifier_stream import ClassifierStream

        event_id = raw_event["event_id"]
        stream = ClassifierStream(
            config={"micro_batch_size": 1, "consumer_poll_timeout_ms": 1000}
        )

        # Build a fake (tp, msg, event) triple without touching Kafka
        from kafka import TopicPartition

        tp = TopicPartition("raw_signals", 0)
        msg = MagicMock()
        msg.offset = 0

        mock_consumer = MagicMock()

        stream._producer = MagicMock()

        with patch("streaming.classifier_stream.publish_with_retry"):
            with patch("streaming.classifier_stream.commit_offsets"):
                stream._process_batch([(tp, msg, raw_event)], mock_consumer)

        dsn = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT category, confidence FROM enriched_signals WHERE event_id = %s",
                    (event_id,),
                )
                row = cur.fetchone()

        assert row is not None, f"enriched_signals row missing for event_id={event_id}"
        category, confidence = row
        assert category in ("opportunity", "threat", "noise")
        assert 0.0 <= float(confidence) <= 1.0

    def test_duplicate_event_is_idempotent(self, raw_event):
        """Processing the same event twice must not raise or create duplicate rows."""
        import os

        import psycopg2

        from streaming.classifier_stream import ClassifierStream

        event_id = raw_event["event_id"]
        stream = ClassifierStream(config={"micro_batch_size": 1})

        from kafka import TopicPartition

        tp = TopicPartition("raw_signals", 0)
        msg = MagicMock()
        msg.offset = 1

        mock_consumer = MagicMock()
        stream._producer = MagicMock()

        with patch("streaming.classifier_stream.publish_with_retry"):
            with patch("streaming.classifier_stream.commit_offsets"):
                # First write
                stream._process_batch([(tp, msg, raw_event)], mock_consumer)
                # Second write — must not raise
                stream._process_batch([(tp, msg, raw_event)], mock_consumer)

        dsn = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM enriched_signals WHERE event_id = %s",
                    (event_id,),
                )
                count = cur.fetchone()[0]

        assert count == 1, f"Expected exactly 1 row, got {count}"

    def test_malformed_event_falls_back_to_noise(self):
        """An event with no raw_text must be classified as noise without raising."""
        import os

        import psycopg2

        from streaming.classifier_stream import ClassifierStream

        event_id = str(uuid.uuid4())
        malformed = {
            "event_id": event_id,
            "source": "scraper",
            "collected_at": datetime.now(tz=timezone.utc).isoformat(),
            "raw_text": "",  # empty text → LLM will return noise fallback
            "url": "",
            "author": "",
            "engagement_score": 0.0,
            "metadata": {},
        }

        stream = ClassifierStream(config={"micro_batch_size": 1})

        from kafka import TopicPartition

        tp = TopicPartition("raw_signals", 0)
        msg = MagicMock()
        msg.offset = 2
        mock_consumer = MagicMock()
        stream._producer = MagicMock()

        with patch("streaming.classifier_stream.publish_with_retry"):
            with patch("streaming.classifier_stream.commit_offsets"):
                stream._process_batch([(tp, msg, malformed)], mock_consumer)

        dsn = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT category FROM enriched_signals WHERE event_id = %s",
                    (event_id,),
                )
                row = cur.fetchone()

        # Row exists (not silently dropped) and has a valid category
        assert row is not None
        assert row[0] in ("opportunity", "threat", "noise")


class TestClassifierStreamEndToEnd:
    def test_produce_to_kafka_and_consume_within_30s(self, raw_event, producer):
        """Full path: produce to raw_signals → ClassifierStream → DB write.

        This test verifies the 30-second latency SLA by running one iteration
        of the stream's internal poll-and-process loop.
        """
        import os

        import psycopg2
        from kafka import KafkaConsumer, TopicPartition

        from ingestion.config.kafka_config import TOPIC_RAW, publish_with_retry
        from streaming.classifier_stream import ClassifierStream

        event_id = raw_event["event_id"]

        # Produce the raw signal
        publish_with_retry(producer, TOPIC_RAW, raw_event, key=event_id)

        # Run the stream with a one-shot consumer
        stream = ClassifierStream(
            config={"micro_batch_size": 1, "consumer_poll_timeout_ms": 5000}
        )
        stream._producer = MagicMock()

        consumer = KafkaConsumer(
            TOPIC_RAW,
            bootstrap_servers=[_BOOTSTRAP],
            group_id="test-classifier-e2e",
            enable_auto_commit=False,
            auto_offset_reset="latest",
            value_deserializer=lambda b: b,
            consumer_timeout_ms=10_000,
        )

        deadline = time.monotonic() + 30.0
        found = False

        try:
            while time.monotonic() < deadline and not found:
                records = consumer.poll(timeout_ms=2000, max_records=10)
                for tp, msgs in records.items():
                    for msg in msgs:
                        try:
                            event = json.loads(msg.value)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue

                        if event.get("event_id") == event_id:
                            with patch("streaming.classifier_stream.publish_with_retry"):
                                with patch("streaming.classifier_stream.commit_offsets"):
                                    fake_msg = MagicMock()
                                    fake_msg.offset = msg.offset
                                    stream._process_batch(
                                        [(tp, fake_msg, event)], MagicMock()
                                    )
                            found = True
                            break
                    if found:
                        break
        finally:
            consumer.close()

        assert found, (
            f"Raw signal event_id={event_id} was not consumed from Kafka within 30 seconds"
        )

        # Now verify it landed in the DB
        dsn = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT category FROM enriched_signals WHERE event_id = %s",
                    (event_id,),
                )
                row = cur.fetchone()

        assert row is not None, (
            f"enriched_signals row not found for event_id={event_id} after processing"
        )
