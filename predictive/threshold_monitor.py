"""Threshold monitor — queries enriched signals, computes MPI per cluster,
and returns clusters that crossed MPI_THRESHOLD.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from predictive.mpi_calculator import MPIResult, calculate_mpi

logger = logging.getLogger(__name__)

MPI_THRESHOLD: float = float(os.environ.get("MPI_THRESHOLD", "0.72"))
SIGNAL_WINDOW_MINUTES: int = int(os.environ.get("SIGNAL_WINDOW_MINUTES", "60"))
MIN_SIGNALS_FOR_CLUSTER: int = 3  # skip clusters with fewer signals


def get_triggered_clusters(
    window_minutes: int = SIGNAL_WINDOW_MINUTES,
    threshold: float = MPI_THRESHOLD,
) -> list[dict]:
    """Return MPI result dicts for clusters that crossed the threshold.

    Each dict is the JSON-serialized MPIResult — ready for Airflow XCom.
    """
    dsn = os.environ.get("POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage")

    signals = _fetch_signals(dsn, window_minutes)
    if not signals:
        logger.info("No enriched signals in the last %d minutes", window_minutes)
        return []

    clusters = _group_by_topic(signals)
    baseline = _compute_global_baseline(dsn, window_minutes)

    triggered: list[dict] = []
    for topic, cluster_signals in clusters.items():
        if len(cluster_signals) < MIN_SIGNALS_FOR_CLUSTER:
            continue

        result = calculate_mpi(
            signals=cluster_signals,
            topic_cluster=topic,
            baseline_avg_signals=baseline,
            window_minutes=window_minutes,
        )
        if result.mpi_score >= threshold:
            logger.info(
                "Threshold crossed: cluster=%r mpi=%.3f threshold=%.3f signals=%d",
                topic,
                result.mpi_score,
                threshold,
                result.signal_count,
            )
            triggered.append(result.model_dump(mode="json"))

    logger.info(
        "%d/%d clusters crossed threshold=%.3f",
        len(triggered),
        len(clusters),
        threshold,
    )
    return triggered


# ── private ───────────────────────────────────────────────────────────────────


def _fetch_signals(dsn: str, window_minutes: int) -> list[dict]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=window_minutes)
    sql = """
        SELECT event_id::text, source, collected_at, category, confidence,
               topic_tags, sentiment, urgency, engagement_score, url, author
        FROM enriched_signals
        WHERE collected_at >= %s
          AND category IN ('opportunity', 'threat')
        ORDER BY collected_at ASC
    """
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (cutoff,))
                rows = cur.fetchall()
    except psycopg2.OperationalError as exc:
        logger.error("DB unavailable in threshold monitor: %s", exc)
        return []

    return [_normalize_row(dict(r)) for r in rows]


def _normalize_row(row: dict) -> dict:
    return {
        **row,
        "confidence": float(row["confidence"] or 0.0),
        "engagement_score": float(row["engagement_score"] or 0.0),
        "topic_tags": row["topic_tags"] or [],
        "author": row.get("author") or "",
        "metadata": {},  # not stored in DB; entity_extractor falls back to URL parsing
    }


def _group_by_topic(signals: list[dict]) -> dict[str, list[dict]]:
    """Group signals by their primary topic tag (first element of topic_tags)."""
    clusters: dict[str, list[dict]] = {}
    for s in signals:
        tags = s.get("topic_tags") or []
        key = tags[0].lower().strip() if tags else "__untagged__"
        clusters.setdefault(key, []).append(s)
    return clusters


def _compute_global_baseline(dsn: str, window_minutes: int) -> float:
    """Average signal count per equivalent window over the past 24 hours."""
    sql = """
        SELECT COALESCE(AVG(bucket_count), 0) AS avg_count
        FROM (
            SELECT
                date_trunc('hour', collected_at) AS bucket,
                COUNT(*) AS bucket_count
            FROM enriched_signals
            WHERE collected_at >= NOW() - INTERVAL '24 hours'
              AND category IN ('opportunity', 'threat')
            GROUP BY bucket
        ) hourly
    """
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        baseline = float(row[0]) if row and row[0] else 10.0
    except psycopg2.OperationalError as exc:
        logger.warning("Could not compute baseline (DB error: %s) — using default 10.0", exc)
        baseline = 10.0

    return max(baseline, 1.0)  # never divide by zero in volume_score
