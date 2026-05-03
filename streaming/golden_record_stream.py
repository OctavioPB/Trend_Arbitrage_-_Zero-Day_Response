"""GoldenRecordStream — triggers Golden Record generation from mpi_update events.

Listens to the mpi_update topic.  When a cluster's MPI crosses MPI_THRESHOLD,
calls generate_and_persist() to create a Golden Record, write it to DB, and
publish golden_record_ready — exactly as the batch path does.

Cooldown
────────
  A per-cluster in-memory cooldown (default 5 min) prevents duplicate Golden
  Records when the MPI oscillates around the threshold.  The cooldown is not
  persisted — on restart it resets, so the first crossing after a restart always
  triggers a record.

Exactly-once
────────────
  Kafka offsets are committed manually after each poll cycle.  generate_and_persist()
  uses INSERT RETURNING with idempotent logic (topic_cluster + created_at bucket).
  If the process crashes between a DB write and an offset commit, the event is
  re-processed but the duplicate DB write is a no-op.

Usage
─────
  python -m streaming.golden_record_stream
  Set ENRICHMENT_MODE=streaming to activate.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from kafka import KafkaConsumer, TopicPartition
from kafka.structs import OffsetAndMetadata

from ingestion.config.kafka_config import BOOTSTRAP_SERVERS
from streaming._offsets import commit_offsets, load_offsets
from streaming.mpi_stream import TOPIC_MPI_UPDATE

logger = logging.getLogger(__name__)

_CONSUMER_GROUP = "golden-record-stream"


def _load_config() -> dict:
    path = Path(os.environ.get("STREAMING_CONFIG_PATH", "config/streaming.json"))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load streaming.json: %s — using defaults", exc)
        return {}


class GoldenRecordStream:
    """Generates Golden Records when MPI events cross the configured threshold."""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or _load_config()
        self._threshold: float = float(os.environ.get("MPI_THRESHOLD", "0.72"))
        self._cooldown_minutes: int = int(cfg.get("golden_record_cooldown_minutes", 5))
        self._poll_timeout_ms: int = int(cfg.get("consumer_poll_timeout_ms", 1000))

        self._dsn: str = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        self._running = False
        self._cooldown: dict[str, datetime] = {}  # cluster → last generation time

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_forever(self) -> None:
        self._running = True
        consumer = self._create_consumer()

        logger.info(
            "GoldenRecordStream started (threshold=%.3f cooldown=%dm)",
            self._threshold,
            self._cooldown_minutes,
        )

        try:
            while self._running:
                records = consumer.poll(timeout_ms=self._poll_timeout_ms)
                kafka_offsets: dict[TopicPartition, OffsetAndMetadata] = {}
                db_offsets: dict[int, int] = {}

                for tp, msgs in records.items():
                    for msg in msgs:
                        try:
                            event = json.loads(msg.value)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            logger.warning("Bad JSON at partition=%d offset=%d", tp.partition, msg.offset)
                        else:
                            if float(event.get("mpi_score", 0.0)) >= self._threshold:
                                self._maybe_generate(event)

                        new_off = msg.offset + 1
                        if tp not in kafka_offsets or new_off > kafka_offsets[tp].offset:
                            kafka_offsets[tp] = OffsetAndMetadata(new_off, None)
                            db_offsets[tp.partition] = new_off

                if kafka_offsets:
                    consumer.commit(kafka_offsets)
                    try:
                        with psycopg2.connect(self._dsn) as conn:
                            commit_offsets(conn, _CONSUMER_GROUP, TOPIC_MPI_UPDATE, db_offsets)
                            conn.commit()
                    except psycopg2.OperationalError as exc:
                        logger.warning("Could not persist offsets to DB: %s", exc)

        finally:
            consumer.close()
            logger.info("GoldenRecordStream stopped")

    def stop(self) -> None:
        self._running = False

    # ── Golden record generation ───────────────────────────────────────────────

    def _maybe_generate(self, event: dict) -> None:
        """Generate a Golden Record if the cluster is not in cooldown."""
        cluster: str = event.get("topic_cluster", "")
        if not cluster:
            return

        last = self._cooldown.get(cluster)
        if last is not None:
            elapsed = datetime.now(tz=timezone.utc) - last
            if elapsed < timedelta(minutes=self._cooldown_minutes):
                logger.debug(
                    "Golden record cooldown active for cluster=%r (%.1fs remaining)",
                    cluster,
                    (timedelta(minutes=self._cooldown_minutes) - elapsed).total_seconds(),
                )
                return

        try:
            from predictive.golden_record_generator import generate_and_persist

            record = generate_and_persist(event)
            self._cooldown[cluster] = datetime.now(tz=timezone.utc)
            logger.info(
                "Golden record generated: id=%s cluster=%r mpi=%.3f",
                record.get("id"),
                cluster,
                event.get("mpi_score"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Golden record generation failed for cluster=%r mpi=%.3f: %s",
                cluster,
                event.get("mpi_score"),
                exc,
            )

    # ── Kafka consumer setup ───────────────────────────────────────────────────

    def _create_consumer(self) -> KafkaConsumer:
        consumer = KafkaConsumer(
            bootstrap_servers=BOOTSTRAP_SERVERS.split(","),
            group_id=_CONSUMER_GROUP,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda b: b,
            consumer_timeout_ms=-1,
        )
        consumer.subscribe([TOPIC_MPI_UPDATE])
        consumer.poll(timeout_ms=5000)
        self._seek_to_stored_offsets(consumer)
        return consumer

    def _seek_to_stored_offsets(self, consumer: KafkaConsumer) -> None:
        try:
            with psycopg2.connect(self._dsn) as conn:
                stored = load_offsets(conn, _CONSUMER_GROUP, TOPIC_MPI_UPDATE)
            for tp in consumer.assignment():
                if tp.partition in stored:
                    consumer.seek(tp, stored[tp.partition])
                    logger.info(
                        "Sought partition=%d to stored offset=%d", tp.partition, stored[tp.partition]
                    )
        except psycopg2.OperationalError as exc:
            logger.warning("Could not load stored offsets: %s", exc)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    mode = os.environ.get("ENRICHMENT_MODE", "batch").lower()
    if mode != "streaming":
        logger.info(
            "ENRICHMENT_MODE=%s — golden-record stream not started (set ENRICHMENT_MODE=streaming)",
            mode,
        )
        return

    GoldenRecordStream().run_forever()


if __name__ == "__main__":
    main()
