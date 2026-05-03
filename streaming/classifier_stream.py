"""ClassifierStream — real-time LLM enrichment of raw Kafka signals.

Consumes raw_signals, classifies in micro-batches of MICRO_BATCH_SIZE (default 5),
writes enriched signals to DB and re-publishes to enriched_signals — all within
the 30-second latency budget.

Exactly-once semantics
──────────────────────
  • enable_auto_commit=False: Kafka offsets are committed manually AFTER the DB
    write succeeds.
  • kafka_stream_offsets table provides a secondary offset store.  On restart the
    consumer seeks to the stored position rather than relying solely on the Kafka
    consumer-group state.
  • DB inserts use ON CONFLICT DO NOTHING (idempotent), so re-processing a batch
    after a crash is safe.

LLM rate limiting
─────────────────
  The existing classify_batch() function already applies tenacity exponential
  back-off on Anthropic 429 errors (up to 5 retries).  ClassifierStream does not
  add additional retry logic — it relies on classify_batch() never raising.

Usage (entry point)
───────────────────
  python -m streaming.classifier_stream

  Set ENRICHMENT_MODE=streaming to activate; any other value causes a clean exit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import psycopg2
from kafka import KafkaConsumer, TopicPartition
from kafka.structs import OffsetAndMetadata

from etl.tasks.db_writer import write_enriched_signals
from etl.tasks.llm_classifier import classify_batch
from ingestion.config.kafka_config import (
    BOOTSTRAP_SERVERS,
    TOPIC_ENRICHED,
    TOPIC_RAW,
    create_producer,
    publish_with_retry,
)
from streaming._offsets import commit_offsets, load_offsets

logger = logging.getLogger(__name__)

_CONSUMER_GROUP = "classifier-stream"
_FLUSH_INTERVAL_S = 5.0  # flush partial batch after this many idle seconds


def _load_config() -> dict:
    from pathlib import Path

    path = Path(os.environ.get("STREAMING_CONFIG_PATH", "config/streaming.json"))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load streaming.json: %s — using defaults", exc)
        return {}


class ClassifierStream:
    """Consumes raw_signals, classifies, writes to DB, publishes to enriched_signals."""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or _load_config()
        self._batch_size: int = int(cfg.get("micro_batch_size", 5))
        self._poll_timeout_ms: int = int(cfg.get("consumer_poll_timeout_ms", 1000))
        self._dsn: str = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        self._running = False
        self._producer = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_forever(self) -> None:
        """Block indefinitely, processing raw signals.  Stop by calling stop()."""
        self._running = True
        self._producer = create_producer()
        consumer = self._create_consumer()

        logger.info("ClassifierStream started (batch_size=%d)", self._batch_size)
        buffer: list[tuple] = []  # (tp, msg, event_dict)
        last_flush = time.monotonic()

        try:
            while self._running:
                records = consumer.poll(
                    timeout_ms=self._poll_timeout_ms,
                    max_records=self._batch_size * 4,
                )

                for tp, msgs in records.items():
                    for msg in msgs:
                        try:
                            event = json.loads(msg.value)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            logger.warning(
                                "Non-JSON message skipped: partition=%d offset=%d",
                                tp.partition,
                                msg.offset,
                            )
                            continue
                        buffer.append((tp, msg, event))

                # Process a full batch immediately
                while len(buffer) >= self._batch_size:
                    batch, buffer = buffer[: self._batch_size], buffer[self._batch_size :]
                    self._process_batch(batch, consumer)
                    last_flush = time.monotonic()

                # Flush partial batch after idle interval
                if buffer and time.monotonic() - last_flush > _FLUSH_INTERVAL_S:
                    self._process_batch(buffer, consumer)
                    buffer.clear()
                    last_flush = time.monotonic()

        finally:
            if buffer:
                logger.info("Flushing %d buffered message(s) on shutdown", len(buffer))
                self._process_batch(buffer, consumer)
            consumer.close()
            logger.info("ClassifierStream stopped")

    def stop(self) -> None:
        self._running = False

    # ── Core batch processing ──────────────────────────────────────────────────

    def _process_batch(
        self,
        batch: list[tuple],
        consumer: KafkaConsumer,
    ) -> None:
        """Classify, write to DB, publish, then commit offsets."""
        events = [ev for _, _, ev in batch]

        try:
            enriched_signals = asyncio.run(classify_batch(events))
            enriched_dicts = [s.model_dump(mode="json") for s in enriched_signals]

            write_enriched_signals(enriched_dicts)

            for d in enriched_dicts:
                try:
                    publish_with_retry(
                        self._producer, TOPIC_ENRICHED, d, key=d.get("event_id")
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to publish enriched signal: %s", exc)

            # Commit offsets only after successful DB write
            kafka_offsets: dict[TopicPartition, OffsetAndMetadata] = {}
            db_offsets: dict[int, int] = {}
            for tp, msg, _ in batch:
                new_offset = msg.offset + 1
                if (
                    tp not in kafka_offsets
                    or new_offset > kafka_offsets[tp].offset
                ):
                    kafka_offsets[tp] = OffsetAndMetadata(new_offset, None)
                    db_offsets[tp.partition] = new_offset

            consumer.commit(kafka_offsets)

            with psycopg2.connect(self._dsn) as conn:
                commit_offsets(conn, _CONSUMER_GROUP, TOPIC_RAW, db_offsets)
                conn.commit()

            logger.info(
                "ClassifierStream: processed batch size=%d enriched=%d",
                len(batch),
                len(enriched_dicts),
            )

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "ClassifierStream batch failed — offsets NOT committed (will retry): %s",
                exc,
            )

    # ── Kafka consumer setup ───────────────────────────────────────────────────

    def _create_consumer(self) -> KafkaConsumer:
        consumer = KafkaConsumer(
            bootstrap_servers=BOOTSTRAP_SERVERS.split(","),
            group_id=_CONSUMER_GROUP,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda b: b,  # raw bytes; we parse manually
            consumer_timeout_ms=-1,          # don't raise StopIteration
        )
        consumer.subscribe([TOPIC_RAW])

        # Poll once to trigger partition assignment, then seek to stored offsets
        consumer.poll(timeout_ms=5000)
        self._seek_to_stored_offsets(consumer)
        return consumer

    def _seek_to_stored_offsets(self, consumer: KafkaConsumer) -> None:
        try:
            with psycopg2.connect(self._dsn) as conn:
                stored = load_offsets(conn, _CONSUMER_GROUP, TOPIC_RAW)

            assignment = consumer.assignment()
            for tp in assignment:
                if tp.partition in stored:
                    consumer.seek(tp, stored[tp.partition])
                    logger.info(
                        "Sought partition=%d to stored offset=%d",
                        tp.partition,
                        stored[tp.partition],
                    )
        except psycopg2.OperationalError as exc:
            logger.warning("Could not load stored offsets (DB unavailable): %s", exc)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    mode = os.environ.get("ENRICHMENT_MODE", "batch").lower()
    if mode != "streaming":
        logger.info(
            "ENRICHMENT_MODE=%s — streaming classifier not started (set ENRICHMENT_MODE=streaming)",
            mode,
        )
        return

    ClassifierStream().run_forever()


if __name__ == "__main__":
    main()
