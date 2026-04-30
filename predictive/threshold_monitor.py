"""Threshold monitor — queries enriched signals, computes MPI per cluster,
and returns clusters that crossed MPI_THRESHOLD.

Public API:
    compute_all_mpi(window_minutes, dsn) → list[dict]
        MPI results for every active cluster, regardless of threshold.
        Used by the archiver to record full history.

    get_triggered_clusters(window_minutes, threshold) → list[dict]
        Subset of compute_all_mpi results that crossed the threshold.
        Used by the golden-record DAG task.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from predictive.mpi_archiver import get_baseline
from predictive.mpi_calculator import MPIResult, calculate_mpi

logger = logging.getLogger(__name__)

MPI_THRESHOLD: float = float(os.environ.get("MPI_THRESHOLD", "0.72"))
SIGNAL_WINDOW_MINUTES: int = int(os.environ.get("SIGNAL_WINDOW_MINUTES", "60"))
MIN_SIGNALS_FOR_CLUSTER: int = 3  # skip clusters with fewer signals

_DSN_DEFAULT = "postgresql://trend:trend@localhost:5432/trend_arbitrage"


def compute_all_mpi(
    window_minutes: int = SIGNAL_WINDOW_MINUTES,
    dsn: str | None = None,
) -> list[dict]:
    """Compute MPI for every active topic cluster in the rolling window.

    Baseline for each cluster is sourced from the 7-day mpi_history average
    (see mpi_archiver.get_baseline). Falls back to 10.0 for new clusters
    with < 1 hour of recorded history.

    Returns:
        List of JSON-serialized MPIResult dicts (all clusters, all scores).
        Empty list if no signals exist in the window.
    """
    dsn = dsn or os.environ.get("POSTGRES_DSN", _DSN_DEFAULT)

    signals = _fetch_signals(dsn, window_minutes)
    if not signals:
        logger.info("No enriched signals in the last %d minutes", window_minutes)
        return []

    clusters = _group_by_topic(signals)

    results: list[dict] = []
    for topic, cluster_signals in clusters.items():
        if len(cluster_signals) < MIN_SIGNALS_FOR_CLUSTER:
            continue

        baseline = get_baseline(dsn, topic, window_minutes)
        result = calculate_mpi(
            signals=cluster_signals,
            topic_cluster=topic,
            baseline_avg_signals=baseline,
            window_minutes=window_minutes,
        )
        results.append(result.model_dump(mode="json"))

    logger.info("compute_all_mpi: %d active cluster(s) computed", len(results))
    return results


def get_triggered_clusters(
    window_minutes: int = SIGNAL_WINDOW_MINUTES,
    threshold: float = MPI_THRESHOLD,
    dsn: str | None = None,
) -> list[dict]:
    """Return MPI result dicts for clusters that crossed the threshold.

    Delegates to compute_all_mpi and filters by threshold.
    Each dict is the JSON-serialized MPIResult — ready for Airflow XCom.
    """
    all_results = compute_all_mpi(window_minutes=window_minutes, dsn=dsn)

    triggered = [r for r in all_results if r["mpi_score"] >= threshold]

    logger.info(
        "%d/%d cluster(s) crossed threshold=%.3f",
        len(triggered),
        len(all_results),
        threshold,
    )
    for r in triggered:
        logger.info(
            "Threshold crossed: cluster=%r mpi=%.3f signals=%d",
            r["topic_cluster"],
            r["mpi_score"],
            r["signal_count"],
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
        "metadata": {},
    }


def _group_by_topic(signals: list[dict]) -> dict[str, list[dict]]:
    """Group signals by their primary topic tag (first element of topic_tags)."""
    clusters: dict[str, list[dict]] = {}
    for s in signals:
        tags = s.get("topic_tags") or []
        key = tags[0].lower().strip() if tags else "__untagged__"
        clusters.setdefault(key, []).append(s)
    return clusters
