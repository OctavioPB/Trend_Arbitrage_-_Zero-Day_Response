"""MPI history archiver — persists per-cluster MPI scores as a time series.

Idempotent: inserting the same (recorded_at_bucket, topic_cluster) twice
runs an ON CONFLICT upsert, never creating a duplicate row.

Public API:
    archive_results(results, dsn) → int          write rows, return count
    get_baseline(dsn_or_conn, topic_cluster, window_minutes) → float
        7-day rolling avg signal_count for the cluster.
        Falls back to _FALLBACK_BASELINE when < 12 history rows exist
        (approximately 1 hour of data at 5-min cadence).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import psycopg2

logger = logging.getLogger(__name__)

_HISTORY_DAYS = 7
_FALLBACK_BASELINE = 10.0
# 12 rows ≈ 1 hour at 5-min cadence — below this the average is not trustworthy
_MIN_ROWS_FOR_BASELINE = 12

_DSN_DEFAULT = "postgresql://trend:trend@localhost:5432/trend_arbitrage"

_UPSERT_SQL = """
    INSERT INTO mpi_history
        (recorded_at, recorded_at_bucket, topic_cluster, mpi_score, signal_count, window_minutes)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (recorded_at_bucket, topic_cluster)
    DO UPDATE SET
        mpi_score    = EXCLUDED.mpi_score,
        signal_count = EXCLUDED.signal_count,
        recorded_at  = EXCLUDED.recorded_at
"""

_BASELINE_SQL = """
    SELECT
        COUNT(*)                       AS row_count,
        COALESCE(AVG(signal_count), 0) AS avg_signals
    FROM mpi_history
    WHERE topic_cluster = %s
      AND window_minutes = %s
      AND recorded_at >= NOW() - (%s * INTERVAL '1 day')
"""

_HISTORY_SQL = """
    SELECT
        recorded_at_bucket AS recorded_at,
        topic_cluster,
        mpi_score,
        signal_count,
        window_minutes
    FROM mpi_history
    WHERE
        (%s IS NULL OR topic_cluster = %s)
        AND recorded_at_bucket >= %s
        AND recorded_at_bucket <= %s
    ORDER BY recorded_at_bucket ASC
    LIMIT %s
"""


# ── Bucket helper ─────────────────────────────────────────────────────────────


def _to_5min_bucket(dt: datetime) -> datetime:
    """Align dt down to the nearest 5-minute boundary."""
    aligned_minute = (dt.minute // 5) * 5
    return dt.replace(minute=aligned_minute, second=0, microsecond=0)


def _parse_computed_at(value: datetime | str | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    if isinstance(value, str):
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ── Write ─────────────────────────────────────────────────────────────────────


def archive_results(results: list[dict], dsn: str | None = None) -> int:
    """Persist MPI results to mpi_history. Returns count of rows written.

    Args:
        results: List of MPIResult dicts (from model_dump or Airflow XCom).
                 Each dict must have topic_cluster, mpi_score, signal_count.
                 Optional keys: computed_at (ISO or datetime), window_minutes.
        dsn:     PostgreSQL DSN. Defaults to POSTGRES_DSN env var.

    Returns:
        Number of rows inserted or updated (0 on failure).
    """
    if not results:
        return 0

    dsn = dsn or os.environ.get("POSTGRES_DSN", _DSN_DEFAULT)
    now = datetime.now(tz=timezone.utc)

    rows = []
    for r in results:
        computed_at = _parse_computed_at(r.get("computed_at"), now)
        bucket = _to_5min_bucket(computed_at)
        rows.append((
            computed_at,
            bucket,
            r["topic_cluster"],
            float(r["mpi_score"]),
            int(r["signal_count"]),
            int(r.get("window_minutes", 60)),
        ))

    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(_UPSERT_SQL, row)
            conn.commit()
    except psycopg2.Error as exc:
        logger.error("Failed to archive %d MPI result(s): %s", len(rows), exc)
        return 0

    logger.info("Archived %d MPI result(s) to mpi_history", len(rows))
    return len(rows)


# ── Read ──────────────────────────────────────────────────────────────────────


def get_baseline(
    dsn_or_conn: str | object,
    topic_cluster: str,
    window_minutes: int = 60,
) -> float:
    """Return the 7-day rolling average signal_count for the cluster.

    Args:
        dsn_or_conn: PostgreSQL DSN string or an open psycopg2 connection.
        topic_cluster: Topic cluster label.
        window_minutes: Window size — only history rows with matching
                        window_minutes are included in the average.

    Returns:
        Average signal count per cycle, clamped to >= 1.0.
        Falls back to _FALLBACK_BASELINE (10.0) when fewer than
        _MIN_ROWS_FOR_BASELINE rows exist (< ~1 hour of data).
    """
    def _run(conn) -> tuple[int, float]:
        with conn.cursor() as cur:
            cur.execute(_BASELINE_SQL, (topic_cluster, window_minutes, _HISTORY_DAYS))
            row = cur.fetchone()
        return int(row[0] or 0), float(row[1] or 0.0)

    try:
        if isinstance(dsn_or_conn, str):
            with psycopg2.connect(dsn_or_conn) as conn:
                row_count, avg_signals = _run(conn)
        else:
            row_count, avg_signals = _run(dsn_or_conn)
    except psycopg2.Error as exc:
        logger.warning(
            "Baseline query failed for cluster=%r: %s — using fallback %.1f",
            topic_cluster,
            exc,
            _FALLBACK_BASELINE,
        )
        return _FALLBACK_BASELINE

    if row_count < _MIN_ROWS_FOR_BASELINE:
        logger.debug(
            "Cluster %r has %d history rows (< %d) — using fallback baseline %.1f",
            topic_cluster,
            row_count,
            _MIN_ROWS_FOR_BASELINE,
            _FALLBACK_BASELINE,
        )
        return _FALLBACK_BASELINE

    return max(avg_signals, 1.0)


def query_history(
    dsn_or_conn: str | object,
    cluster: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    limit: int = 500,
) -> list[dict]:
    """Fetch MPI history rows for the history API endpoint.

    Args:
        dsn_or_conn: DSN string or open psycopg2 connection.
        cluster:     Filter by topic_cluster (None = all clusters).
        from_dt:     Lower bound for recorded_at_bucket (inclusive).
        to_dt:       Upper bound for recorded_at_bucket (inclusive).
        limit:       Maximum number of rows to return.

    Returns:
        List of dicts with keys: recorded_at, topic_cluster, mpi_score,
        signal_count, window_minutes.
    """
    import psycopg2.extras

    now = datetime.now(tz=timezone.utc)
    from datetime import timedelta
    resolved_from = from_dt or (now - timedelta(days=_HISTORY_DAYS))
    resolved_to = to_dt or now

    def _run(conn) -> list[dict]:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                _HISTORY_SQL,
                (cluster, cluster, resolved_from, resolved_to, limit),
            )
            return [dict(r) for r in cur.fetchall()]

    try:
        if isinstance(dsn_or_conn, str):
            with psycopg2.connect(dsn_or_conn) as conn:
                return _run(conn)
        else:
            return _run(dsn_or_conn)
    except psycopg2.Error as exc:
        logger.error("History query failed: %s", exc)
        return []
