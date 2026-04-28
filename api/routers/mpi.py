"""MPI router — current MPI heat map grid (topic clusters × 5-min time buckets)."""

import logging
from collections import defaultdict
from datetime import datetime, timezone

import psycopg2.extras
from fastapi import APIRouter, Query

from api.db import get_conn
from api.schemas.models import MPICell, MPIGridResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mpi", tags=["mpi"])


@router.get("", response_model=MPIGridResponse)
def get_mpi_grid(
    window_minutes: int = Query(default=60, ge=5, le=1440),
) -> MPIGridResponse:
    now = datetime.now(tz=timezone.utc)
    cells = _build_mpi_grid(window_minutes, now)

    topic_clusters = sorted({c.topic_cluster for c in cells})
    time_buckets = sorted({c.time_bucket for c in cells})

    return MPIGridResponse(
        computed_at=now,
        window_minutes=window_minutes,
        cells=cells,
        topic_clusters=topic_clusters,
        time_buckets=time_buckets,
    )


def build_mpi_grid_dict(window_minutes: int = 60) -> dict:
    """Build the MPI grid and return a JSON-serializable dict.

    Used by the WebSocket endpoint (called via asyncio.to_thread).
    """
    now = datetime.now(tz=timezone.utc)
    response = MPIGridResponse(
        computed_at=now,
        window_minutes=window_minutes,
        cells=_build_mpi_grid(window_minutes, now),
        topic_clusters=[],
        time_buckets=[],
    )
    # Populate derived fields
    response = MPIGridResponse(
        computed_at=now,
        window_minutes=window_minutes,
        cells=response.cells,
        topic_clusters=sorted({c.topic_cluster for c in response.cells}),
        time_buckets=sorted({c.time_bucket for c in response.cells}),
    )
    return response.model_dump(mode="json")


# ── private ───────────────────────────────────────────────────────────────────


_MPI_GRID_SQL = """
    SELECT
        topic_tags[1]                                      AS primary_topic,
        date_trunc('minute', collected_at)
            - ((EXTRACT(MINUTE FROM collected_at)::int %% 5) * INTERVAL '1 minute')
                                                           AS time_bucket,
        COUNT(*)                                           AS signal_count,
        COALESCE(
            SUM(CASE WHEN sentiment = 'positive' THEN 1.0 ELSE 0.0 END)
                / NULLIF(COUNT(*), 0),
            0.0
        )                                                  AS sentiment_ratio
    FROM enriched_signals
    WHERE collected_at >= NOW() - (%s * INTERVAL '1 minute')
      AND category IN ('opportunity', 'threat')
      AND topic_tags IS NOT NULL
      AND array_length(topic_tags, 1) > 0
    GROUP BY primary_topic, time_bucket
    ORDER BY time_bucket ASC, primary_topic ASC
"""


def _build_mpi_grid(window_minutes: int, now: datetime) -> list[MPICell]:
    """Fetch signal aggregates from DB and compute per-cell heat map scores."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_MPI_GRID_SQL, (window_minutes,))
            rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return []

    # Normalize by max count across all cells so relative intensity makes sense
    max_count = max(int(r["signal_count"]) for r in rows)

    cells: list[MPICell] = []
    for row in rows:
        count = int(row["signal_count"])
        sentiment_ratio = float(row["sentiment_ratio"])
        volume_factor = count / max(max_count, 1)
        score = min(volume_factor * 0.7 + sentiment_ratio * 0.3, 1.0)

        cells.append(
            MPICell(
                topic_cluster=row["primary_topic"],
                time_bucket=row["time_bucket"],
                score=round(score, 3),
                signal_count=count,
                sentiment_score=round(sentiment_ratio, 3),
            )
        )
    return cells
