"""History router — MPI time-series query endpoint.

GET /history/mpi
    Returns persisted MPI scores from mpi_history. Used by analytics views
    and to verify baseline calibration over time.

This endpoint is intentionally read-only. All writes go through the
archive_mpi DAG task via mpi_archiver.archive_results().
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.db import get_conn
from predictive.mpi_archiver import query_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["history"])

_MAX_LIMIT = 5000


# ── Response models ───────────────────────────────────────────────────────────


class MPIHistoryPoint(BaseModel):
    recorded_at: str
    topic_cluster: str
    mpi_score: float
    signal_count: int
    window_minutes: int


class MPIHistoryResponse(BaseModel):
    points: list[MPIHistoryPoint]
    total: int
    from_dt: str
    to_dt: str


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.get("/mpi", response_model=MPIHistoryResponse)
def get_mpi_history(
    cluster: str | None = Query(
        default=None,
        description="Filter by topic cluster name. Omit to return all clusters.",
    ),
    from_dt: str | None = Query(
        default=None,
        description=(
            "ISO 8601 datetime lower bound (inclusive). "
            "Defaults to 7 days ago."
        ),
    ),
    to_dt: str | None = Query(
        default=None,
        description="ISO 8601 datetime upper bound (inclusive). Defaults to now.",
    ),
    limit: int = Query(
        default=500,
        ge=1,
        le=_MAX_LIMIT,
        description=f"Maximum rows to return (max {_MAX_LIMIT}).",
    ),
) -> MPIHistoryResponse:
    """Return MPI time-series data from mpi_history, sorted by recorded_at ascending."""
    now = datetime.now(tz=timezone.utc)

    resolved_from, resolved_to = _parse_bounds(from_dt, to_dt, now)

    if resolved_from >= resolved_to:
        raise HTTPException(
            status_code=422,
            detail="from_dt must be earlier than to_dt",
        )

    with get_conn() as conn:
        rows = query_history(
            dsn_or_conn=conn,
            cluster=cluster,
            from_dt=resolved_from,
            to_dt=resolved_to,
            limit=limit,
        )

    points = [
        MPIHistoryPoint(
            recorded_at=_to_iso(r["recorded_at"]),
            topic_cluster=r["topic_cluster"],
            mpi_score=float(r["mpi_score"]),
            signal_count=int(r["signal_count"]),
            window_minutes=int(r["window_minutes"]),
        )
        for r in rows
    ]

    return MPIHistoryResponse(
        points=points,
        total=len(points),
        from_dt=resolved_from.isoformat(),
        to_dt=resolved_to.isoformat(),
    )


# ── helpers ───────────────────────────────────────────────────────────────────


def _parse_bounds(
    from_str: str | None,
    to_str: str | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    default_from = now - timedelta(days=7)
    default_to = now

    try:
        resolved_from = _parse_dt(from_str) if from_str else default_from
        resolved_to = _parse_dt(to_str) if to_str else default_to
    except (ValueError, OverflowError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid datetime format: {exc}. Use ISO 8601 (e.g. 2026-04-29T12:00:00Z).",
        ) from exc

    return resolved_from, resolved_to


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_iso(value: datetime | str) -> str:
    if isinstance(value, str):
        return value
    return value.isoformat()
