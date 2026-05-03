"""MPIStream — real-time MPI recomputation from the enriched_signals topic.

Maintains a per-cluster in-memory rolling window of enriched signals.
On every new signal, recomputes MPI for that cluster (debounced) and publishes
a mpi_update event to TOPIC_MPI_UPDATE when the score changes by more than
mpi_change_threshold (default 0.05).

In-memory design
────────────────
  Signals are never fetched from DB during steady-state processing.  The rolling
  window is rebuilt from Kafka on restart (consumer seeks to stored offset and
  replays the enriched_signals topic from that point forward).

Baseline cache
──────────────
  Baseline signal count per cluster is fetched once from mpi_history and cached
  for baseline_cache_ttl_minutes (default 5).  Falls back to the module-level
  _FALLBACK_BASELINE when the DB is unavailable.

Debounce
────────
  A cluster's MPI is recomputed at most once per mpi_recompute_debounce_ms to
  avoid thrashing during signal bursts.

Usage
─────
  python -m streaming.mpi_stream
  Set ENRICHMENT_MODE=streaming to activate.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from kafka import KafkaConsumer, TopicPartition
from kafka.structs import OffsetAndMetadata

from ingestion.config.kafka_config import (
    BOOTSTRAP_SERVERS,
    TOPIC_ENRICHED,
    create_producer,
    publish_with_retry,
)
from predictive.mpi_calculator import calculate_mpi, load_source_weights, load_weights
from streaming._offsets import commit_offsets, load_offsets

logger = logging.getLogger(__name__)

TOPIC_MPI_UPDATE: str = os.environ.get("KAFKA_TOPIC_MPI_UPDATE", "mpi_update")

_CONSUMER_GROUP = "mpi-stream"
_FALLBACK_BASELINE = 10.0


def _load_config() -> dict:
    path = Path(os.environ.get("STREAMING_CONFIG_PATH", "config/streaming.json"))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load streaming.json: %s — using defaults", exc)
        return {}


class _ClusterWindow:
    """Fixed-duration rolling window of enriched signal dicts for one cluster."""

    def __init__(self, window_minutes: int) -> None:
        self._cutoff_delta = timedelta(minutes=window_minutes)
        self._signals: deque[dict] = deque()

    def add(self, signal: dict) -> None:
        collected_at = signal.get("collected_at")
        if isinstance(collected_at, str):
            try:
                collected_at = datetime.fromisoformat(collected_at)
                if collected_at.tzinfo is None:
                    collected_at = collected_at.replace(tzinfo=timezone.utc)
            except ValueError:
                collected_at = datetime.now(tz=timezone.utc)
        self._signals.append({**signal, "collected_at": collected_at})
        self._evict()

    def get_signals(self) -> list[dict]:
        self._evict()
        return list(self._signals)

    def _evict(self) -> None:
        cutoff = datetime.now(tz=timezone.utc) - self._cutoff_delta
        while self._signals and self._signals[0]["collected_at"] < cutoff:
            self._signals.popleft()


class MPIStream:
    """Maintains in-memory rolling windows and publishes mpi_update events."""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or _load_config()
        self._window_minutes: int = int(cfg.get("rolling_window_minutes", 60))
        self._debounce_s: float = float(cfg.get("mpi_recompute_debounce_ms", 500)) / 1000.0
        self._change_threshold: float = float(cfg.get("mpi_change_threshold", 0.05))
        self._poll_timeout_ms: int = int(cfg.get("consumer_poll_timeout_ms", 1000))
        self._baseline_cache_ttl_s: float = (
            float(cfg.get("baseline_cache_ttl_minutes", 5)) * 60.0
        )

        self._dsn: str = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        self._running = False

        # Per-cluster state (all in-memory)
        self._windows: dict[str, _ClusterWindow] = {}
        self._last_mpi: dict[str, float] = {}
        self._last_computed: dict[str, float] = {}   # monotonic
        self._baseline_cache: dict[str, tuple[float, float]] = {}  # value, mono ts

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_forever(self) -> None:
        self._running = True
        producer = create_producer()
        consumer = self._create_consumer()

        logger.info(
            "MPIStream started (window=%dm debounce=%.1fs change_threshold=%.2f)",
            self._window_minutes,
            self._debounce_s,
            self._change_threshold,
        )

        try:
            while self._running:
                records = consumer.poll(timeout_ms=self._poll_timeout_ms)
                kafka_offsets: dict[TopicPartition, OffsetAndMetadata] = {}
                db_offsets: dict[int, int] = {}

                for tp, msgs in records.items():
                    for msg in msgs:
                        try:
                            signal = json.loads(msg.value)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            logger.warning("Bad JSON at partition=%d offset=%d", tp.partition, msg.offset)
                            kafka_offsets[tp] = OffsetAndMetadata(msg.offset + 1, None)
                            db_offsets[tp.partition] = msg.offset + 1
                            continue

                        cluster = signal.get("topic_cluster") or _infer_cluster(signal)
                        if cluster:
                            self._on_signal(signal, cluster, producer)

                        new_off = msg.offset + 1
                        if tp not in kafka_offsets or new_off > kafka_offsets[tp].offset:
                            kafka_offsets[tp] = OffsetAndMetadata(new_off, None)
                            db_offsets[tp.partition] = new_off

                if kafka_offsets:
                    consumer.commit(kafka_offsets)
                    try:
                        with psycopg2.connect(self._dsn) as conn:
                            commit_offsets(conn, _CONSUMER_GROUP, TOPIC_ENRICHED, db_offsets)
                            conn.commit()
                    except psycopg2.OperationalError as exc:
                        logger.warning("Could not persist offsets to DB: %s", exc)

        finally:
            consumer.close()
            logger.info("MPIStream stopped")

    def stop(self) -> None:
        self._running = False

    # ── Signal handler ─────────────────────────────────────────────────────────

    def _on_signal(self, signal: dict, cluster: str, producer) -> None:
        """Add signal to window and recompute MPI (debounced)."""
        if cluster not in self._windows:
            self._windows[cluster] = _ClusterWindow(self._window_minutes)
        self._windows[cluster].add(signal)

        # Debounce: skip recomputation if we just computed this cluster
        now_mono = time.monotonic()
        if now_mono - self._last_computed.get(cluster, 0.0) < self._debounce_s:
            return
        self._last_computed[cluster] = now_mono

        signals = self._windows[cluster].get_signals()
        if not signals:
            return

        baseline = self._get_baseline(cluster)
        try:
            result = calculate_mpi(
                signals=signals,
                topic_cluster=cluster,
                baseline_avg_signals=baseline,
                window_minutes=self._window_minutes,
                weights=load_weights(),
                source_weights=load_source_weights(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("MPI computation failed for cluster=%r: %s", cluster, exc)
            return

        mpi_score = result.mpi_score
        prev_mpi = self._last_mpi.get(cluster, -1.0)

        if abs(mpi_score - prev_mpi) >= self._change_threshold:
            self._publish_mpi_update(producer, result)
            self._last_mpi[cluster] = mpi_score

    # ── Kafka helpers ──────────────────────────────────────────────────────────

    def _publish_mpi_update(self, producer, result) -> None:
        event = {
            "event_type": "mpi_update",
            "topic_cluster": result.topic_cluster,
            "mpi_score": result.mpi_score,
            "velocity_score": result.velocity_score,
            "volume_score": result.volume_score,
            "sentiment_score": result.sentiment_score,
            "signal_count": result.signal_count,
            "computed_at": result.computed_at.isoformat(),
        }
        try:
            publish_with_retry(producer, TOPIC_MPI_UPDATE, event, key=result.topic_cluster)
            logger.debug(
                "mpi_update published: cluster=%r mpi=%.3f", result.topic_cluster, result.mpi_score
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to publish mpi_update for cluster=%r: %s", result.topic_cluster, exc)

    def _create_consumer(self) -> KafkaConsumer:
        consumer = KafkaConsumer(
            bootstrap_servers=BOOTSTRAP_SERVERS.split(","),
            group_id=_CONSUMER_GROUP,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda b: b,
            consumer_timeout_ms=-1,
        )
        consumer.subscribe([TOPIC_ENRICHED])
        consumer.poll(timeout_ms=5000)
        self._seek_to_stored_offsets(consumer)
        return consumer

    def _seek_to_stored_offsets(self, consumer: KafkaConsumer) -> None:
        try:
            with psycopg2.connect(self._dsn) as conn:
                stored = load_offsets(conn, _CONSUMER_GROUP, TOPIC_ENRICHED)
            for tp in consumer.assignment():
                if tp.partition in stored:
                    consumer.seek(tp, stored[tp.partition])
                    logger.info("Sought partition=%d to stored offset=%d", tp.partition, stored[tp.partition])
        except psycopg2.OperationalError as exc:
            logger.warning("Could not load stored offsets: %s", exc)

    # ── Baseline cache ─────────────────────────────────────────────────────────

    def _get_baseline(self, cluster: str) -> float:
        now_mono = time.monotonic()
        if cluster in self._baseline_cache:
            value, ts = self._baseline_cache[cluster]
            if now_mono - ts < self._baseline_cache_ttl_s:
                return value

        try:
            from predictive.mpi_archiver import get_baseline as _get_baseline_db

            baseline = _get_baseline_db(self._dsn, cluster, self._window_minutes)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Baseline fetch failed for cluster=%r: %s — using fallback", cluster, exc)
            baseline = _FALLBACK_BASELINE

        self._baseline_cache[cluster] = (baseline, now_mono)
        return baseline


# ── Helpers ───────────────────────────────────────────────────────────────────


def _infer_cluster(signal: dict) -> str | None:
    """Derive topic_cluster from topic_tags if the field is absent."""
    tags: list[str] = signal.get("topic_tags") or []
    return tags[0] if tags else None


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    mode = os.environ.get("ENRICHMENT_MODE", "batch").lower()
    if mode != "streaming":
        logger.info(
            "ENRICHMENT_MODE=%s — MPI stream not started (set ENRICHMENT_MODE=streaming)",
            mode,
        )
        return

    MPIStream().run_forever()


if __name__ == "__main__":
    main()
