"""Golden record generator — produces and persists a golden record when MPI crosses threshold.

expires_at is computed from velocity decay, NOT a fixed offset from created_at.
High-velocity trends saturate faster → shorter TTL.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from etl.tasks.entity_extractor import extract_audience_proxy
from ingestion.config.kafka_config import (
    TOPIC_ENRICHED,
    create_producer,
    publish_with_retry,
)

logger = logging.getLogger(__name__)

TOPIC_GOLDEN_READY = "golden_record_ready"

# Velocity-based TTL constants
_BASE_TTL_HOURS = 8.0   # TTL when velocity_score = 0.0 (slow-moving trend)
_MIN_TTL_HOURS = 1.0    # TTL when velocity_score = 1.0 (viral, saturates fast)


def generate_and_persist(mpi_result_dict: dict) -> str:
    """Generate a golden record for the triggered cluster, write to DB, publish to Kafka.

    Args:
        mpi_result_dict: JSON-serialized MPIResult dict (from threshold_monitor).

    Returns:
        UUID string of the created golden record.
    """
    dsn = os.environ.get("POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage")
    now = datetime.now(tz=timezone.utc)

    topic_cluster: str = mpi_result_dict["topic_cluster"]
    mpi_score: float = mpi_result_dict["mpi_score"]
    velocity_score: float = mpi_result_dict["velocity_score"]
    signal_count: int = mpi_result_dict["signal_count"]
    window_minutes: int = int(os.environ.get("SIGNAL_WINDOW_MINUTES", "60"))

    # Fetch the signals that form this cluster for audience proxy
    signals = _fetch_cluster_signals(dsn, topic_cluster, window_minutes)
    audience_proxy = extract_audience_proxy(signals)
    recommended_action = _make_recommended_action(topic_cluster, mpi_score)
    expires_at = _compute_expires_at(velocity_score, now)

    record_id = _write_golden_record(
        dsn=dsn,
        topic_cluster=topic_cluster,
        mpi_score=mpi_score,
        signal_count=signal_count,
        audience_proxy=audience_proxy,
        recommended_action=recommended_action,
        expires_at=expires_at,
    )

    _publish_golden_record_ready(
        record_id=record_id,
        topic_cluster=topic_cluster,
        mpi_score=mpi_score,
        expires_at=expires_at,
    )

    logger.info(
        "Golden record created: id=%s cluster=%r mpi=%.3f expires_at=%s",
        record_id,
        topic_cluster,
        mpi_score,
        expires_at.isoformat(),
    )
    return record_id


def _compute_expires_at(velocity_score: float, now: datetime) -> datetime:
    """Compute TTL based on velocity.

    High velocity → trend saturates quickly → shorter TTL.
    Range: [_MIN_TTL_HOURS, _BASE_TTL_HOURS] depending on velocity.
    """
    ttl_hours = _BASE_TTL_HOURS - (velocity_score * (_BASE_TTL_HOURS - _MIN_TTL_HOURS))
    ttl_hours = max(ttl_hours, _MIN_TTL_HOURS)
    return now + timedelta(hours=ttl_hours)


def _make_recommended_action(topic_cluster: str, mpi_score: float) -> str:
    if mpi_score >= 0.9:
        return (
            f"URGENT: Activate paid acquisition for '{topic_cluster}' — "
            "trend is at peak. Window is closing within hours."
        )
    elif mpi_score >= 0.72:
        return (
            f"Prepare audience segment for '{topic_cluster}' — "
            "momentum is building. Launch within 24 hours."
        )
    return f"Monitor '{topic_cluster}' — MPI above threshold but pace is moderate."


def _fetch_cluster_signals(dsn: str, topic_cluster: str, window_minutes: int) -> list[dict]:
    """Fetch enriched signals for the given topic cluster from the rolling window."""
    sql = """
        SELECT event_id::text, source, url, author, topic_tags,
               sentiment, urgency, engagement_score
        FROM enriched_signals
        WHERE collected_at >= NOW() - INTERVAL '%s minutes'
          AND category IN ('opportunity', 'threat')
          AND %s = ANY(topic_tags)
        ORDER BY collected_at ASC
        LIMIT 500
    """
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (window_minutes, topic_cluster))
                rows = cur.fetchall()
        return [
            {
                **dict(r),
                "topic_tags": r["topic_tags"] or [],
                "metadata": {},
            }
            for r in rows
        ]
    except psycopg2.OperationalError as exc:
        logger.warning("DB error fetching cluster signals: %s — using empty audience proxy", exc)
        return []


def _write_golden_record(
    dsn: str,
    topic_cluster: str,
    mpi_score: float,
    signal_count: int,
    audience_proxy: dict[str, Any],
    recommended_action: str,
    expires_at: datetime,
) -> str:
    sql = """
        INSERT INTO golden_records
            (topic_cluster, mpi_score, signal_count, audience_proxy,
             recommended_action, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id::text
    """
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    topic_cluster,
                    mpi_score,
                    signal_count,
                    json.dumps(audience_proxy),
                    recommended_action,
                    expires_at,
                ),
            )
            record_id: str = cur.fetchone()[0]
        conn.commit()
    return record_id


def _publish_golden_record_ready(
    record_id: str,
    topic_cluster: str,
    mpi_score: float,
    expires_at: datetime,
) -> None:
    event = {
        "event_type": "golden_record_ready",
        "golden_record_id": record_id,
        "topic_cluster": topic_cluster,
        "mpi_score": mpi_score,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    try:
        producer = create_producer()
        publish_with_retry(producer, TOPIC_GOLDEN_READY, event, key=record_id)
    except Exception as exc:  # noqa: BLE001 — Kafka down must not roll back the DB write
        logger.error(
            "Failed to publish golden_record_ready for id=%s: %s — DB record is persisted",
            record_id,
            exc,
        )
