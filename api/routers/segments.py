"""Segments router — active Golden Records with audience proxy and expiry countdown."""

import json
import logging

import psycopg2.extras
from fastapi import APIRouter

from api.db import get_conn
from api.schemas.models import GoldenRecordListResponse, GoldenRecordResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/segments", tags=["segments"])

_LIST_SQL = """
    SELECT
        id::text,
        created_at,
        topic_cluster,
        mpi_score,
        signal_count,
        audience_proxy,
        recommended_action,
        expires_at
    FROM golden_records
    WHERE expires_at > NOW()
    ORDER BY mpi_score DESC, created_at DESC
    LIMIT 100
"""


@router.get("", response_model=GoldenRecordListResponse)
def list_active_segments() -> GoldenRecordListResponse:
    """Return active Golden Records (non-expired), ordered by MPI score descending."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_LIST_SQL)
            rows = [dict(r) for r in cur.fetchall()]

    records = [_row_to_record(r) for r in rows]
    return GoldenRecordListResponse(records=records, total=len(records))


def _row_to_record(row: dict) -> GoldenRecordResponse:
    audience_proxy = row.get("audience_proxy") or {}
    if isinstance(audience_proxy, str):
        try:
            audience_proxy = json.loads(audience_proxy)
        except json.JSONDecodeError:
            audience_proxy = {}

    return GoldenRecordResponse(
        id=row["id"],
        created_at=row["created_at"],
        topic_cluster=row["topic_cluster"],
        mpi_score=float(row["mpi_score"] or 0.0),
        signal_count=int(row["signal_count"] or 0),
        audience_proxy=audience_proxy,
        recommended_action=row.get("recommended_action") or "",
        expires_at=row["expires_at"],
    )
