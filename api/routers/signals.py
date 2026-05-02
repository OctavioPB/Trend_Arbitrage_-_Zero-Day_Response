"""Signals router — enriched signal listing with filtering."""

import logging
from datetime import datetime, timezone

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import require_scope
from api.db import get_conn
from api.schemas.models import SignalListResponse, SignalResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])

_VALID_CATEGORIES = {"opportunity", "threat", "noise"}
_VALID_URGENCIES = {"low", "medium", "high"}
_VALID_SOURCES = {"reddit", "twitter", "scraper"}


@router.get("", response_model=SignalListResponse)
def list_signals(
    category: str | None = Query(default=None, description="opportunity | threat | noise"),
    urgency: str | None = Query(default=None, description="low | medium | high"),
    source: str | None = Query(default=None, description="reddit | twitter | scraper"),
    from_dt: datetime | None = Query(default=None, description="ISO8601 lower bound on collected_at"),
    to_dt: datetime | None = Query(default=None, description="ISO8601 upper bound on collected_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    _subject: str = Depends(require_scope("read:signals")),
) -> SignalListResponse:
    if category and category not in _VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {sorted(_VALID_CATEGORIES)}")
    if urgency and urgency not in _VALID_URGENCIES:
        raise HTTPException(status_code=422, detail=f"urgency must be one of {sorted(_VALID_URGENCIES)}")
    if source and source not in _VALID_SOURCES:
        raise HTTPException(status_code=422, detail=f"source must be one of {sorted(_VALID_SOURCES)}")

    where_clauses = ["1=1"]
    params: list = []

    if category:
        where_clauses.append("category = %s")
        params.append(category)
    if urgency:
        where_clauses.append("urgency = %s")
        params.append(urgency)
    if source:
        where_clauses.append("source = %s")
        params.append(source)
    if from_dt:
        where_clauses.append("collected_at >= %s")
        params.append(from_dt)
    if to_dt:
        where_clauses.append("collected_at <= %s")
        params.append(to_dt)

    where_sql = " AND ".join(where_clauses)
    offset = (page - 1) * page_size

    count_sql = f"SELECT COUNT(*) FROM enriched_signals WHERE {where_sql}"
    data_sql = f"""
        SELECT id::text, event_id::text, source, collected_at, enriched_at,
               category, confidence, topic_tags, sentiment, urgency,
               engagement_score, url, reasoning
        FROM enriched_signals
        WHERE {where_sql}
        ORDER BY collected_at DESC
        LIMIT %s OFFSET %s
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(count_sql, params)
            total: int = cur.fetchone()["count"]

            cur.execute(data_sql, params + [page_size, offset])
            rows = cur.fetchall()

    signals = [_row_to_signal(dict(r)) for r in rows]
    return SignalListResponse(signals=signals, total=total, page=page, page_size=page_size)


def _row_to_signal(row: dict) -> SignalResponse:
    return SignalResponse(
        id=row["id"],
        event_id=row["event_id"],
        source=row["source"],
        collected_at=row["collected_at"],
        enriched_at=row.get("enriched_at"),
        category=row["category"] or "noise",
        confidence=float(row["confidence"] or 0.0),
        topic_tags=row["topic_tags"] or [],
        sentiment=row["sentiment"] or "neutral",
        urgency=row["urgency"] or "low",
        engagement_score=float(row["engagement_score"] or 0.0),
        url=row.get("url") or "",
        reasoning=row.get("reasoning") or "",
    )
