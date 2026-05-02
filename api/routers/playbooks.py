"""Playbooks router — list definitions, dry-run test, execution history.

GET  /playbooks          — list enabled playbook definitions from config
POST /playbooks/test     — dry-run engine against a synthetic golden record
GET  /playbooks/runs     — query playbook_runs execution history
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import require_scope
from api.db import get_conn
from playbooks.engine import ActionResult, PlaybookEngine, PlaybookRunResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

_MAX_RUNS_LIMIT = 500


# ── Request / Response models ─────────────────────────────────────────────────


class PlaybookTrigger(BaseModel):
    min_mpi: float
    topic_cluster_pattern: str
    urgency: list[str] | str | None


class PlaybookDefinition(BaseModel):
    name: str
    description: str
    enabled: bool
    trigger: PlaybookTrigger
    cooldown_minutes: int
    actions: list[dict[str, Any]]


class ActionResultResponse(BaseModel):
    action_type: str
    success: bool
    dry_run: bool
    detail: str
    error: str | None = None


class PlaybookRunResponse(BaseModel):
    playbook_name: str
    topic_cluster: str
    triggered: bool
    dry_run: bool
    cooldown_skipped: bool
    actions: list[ActionResultResponse]
    status: str
    run_id: str | None = None


class PlaybookTestRequest(BaseModel):
    topic_cluster: str = Field(default="ai-chips")
    mpi_score: float = Field(default=0.88, ge=0.0, le=1.0)
    signal_count: int = Field(default=10, ge=1)
    urgency: str = Field(default="high")
    audience_proxy: dict[str, Any] = Field(default_factory=dict)
    playbook_name: str | None = Field(
        default=None,
        description="If specified, only this playbook is evaluated.",
    )


class PlaybookRunHistoryItem(BaseModel):
    id: str
    golden_record_id: str
    playbook_name: str
    topic_cluster: str
    actions_taken: list[dict[str, Any]]
    dry_run: bool
    status: str
    started_at: str
    completed_at: str | None


class PlaybookRunHistoryResponse(BaseModel):
    runs: list[PlaybookRunHistoryItem]
    total: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[PlaybookDefinition])
def list_playbooks(
    _subject: str = Depends(require_scope("read:segments")),
) -> list[PlaybookDefinition]:
    """Return all enabled playbook definitions from config/playbooks.json."""
    engine = PlaybookEngine()
    raw = engine.load_playbooks()
    results = []
    for p in raw:
        trigger_raw = p.get("trigger") or {}
        try:
            results.append(
                PlaybookDefinition(
                    name=p.get("name", ""),
                    description=p.get("description", ""),
                    enabled=p.get("enabled", True),
                    trigger=PlaybookTrigger(
                        min_mpi=float(trigger_raw.get("min_mpi", 0.0)),
                        topic_cluster_pattern=trigger_raw.get("topic_cluster_pattern", "*"),
                        urgency=trigger_raw.get("urgency"),
                    ),
                    cooldown_minutes=int(p.get("cooldown_minutes", 60)),
                    actions=list(p.get("actions") or []),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed playbook %r: %s", p.get("name"), exc)
    return results


@router.post("/test", response_model=list[PlaybookRunResponse])
def test_playbooks(
    body: PlaybookTestRequest,
    _subject: str = Depends(require_scope("write:alerts")),
) -> list[PlaybookRunResponse]:
    """Dry-run the playbook engine against a synthetic golden record.

    No external APIs are called. Results are persisted to playbook_runs
    with dry_run=True so they appear in the history endpoint.
    """
    synthetic_record: dict[str, Any] = {
        "id": "",  # no real golden_record_id — engine skips DB persist
        "topic_cluster": body.topic_cluster,
        "mpi_score": body.mpi_score,
        "signal_count": body.signal_count,
        "urgency": body.urgency,
        "audience_proxy": body.audience_proxy,
        "recommended_action": "",
        "expires_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    engine = PlaybookEngine()

    if body.playbook_name:
        playbooks = [
            p for p in engine.load_playbooks() if p.get("name") == body.playbook_name
        ]
        if not playbooks:
            raise HTTPException(
                status_code=404,
                detail=f"Playbook {body.playbook_name!r} not found",
            )
        # Temporarily patch the engine to only evaluate the requested playbook
        engine._patched_playbooks = playbooks  # type: ignore[attr-defined]
        _orig_load = engine.load_playbooks
        engine.load_playbooks = lambda: playbooks  # type: ignore[method-assign]

    results = engine.run(synthetic_record, dry_run=True)
    return [_result_to_response(r) for r in results]


@router.get("/runs", response_model=PlaybookRunHistoryResponse)
def get_playbook_runs(
    _subject: str = Depends(require_scope("read:segments")),
    playbook_name: str | None = Query(default=None),
    topic_cluster: str | None = Query(default=None),
    dry_run: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=_MAX_RUNS_LIMIT),
) -> PlaybookRunHistoryResponse:
    """Return execution history from playbook_runs, newest first."""
    filters: list[str] = []
    params: list[Any] = []

    if playbook_name is not None:
        filters.append("playbook_name = %s")
        params.append(playbook_name)
    if topic_cluster is not None:
        filters.append("topic_cluster = %s")
        params.append(topic_cluster)
    if dry_run is not None:
        filters.append("dry_run = %s")
        params.append(dry_run)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params.append(limit)

    sql = f"""
        SELECT id::text, golden_record_id::text, playbook_name, topic_cluster,
               actions_taken, dry_run, status, started_at, completed_at
        FROM playbook_runs
        {where}
        ORDER BY started_at DESC
        LIMIT %s
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]

    items = [
        PlaybookRunHistoryItem(
            id=r["id"],
            golden_record_id=r["golden_record_id"],
            playbook_name=r["playbook_name"],
            topic_cluster=r["topic_cluster"],
            actions_taken=r["actions_taken"] if isinstance(r["actions_taken"], list) else [],
            dry_run=r["dry_run"],
            status=r["status"],
            started_at=_iso(r["started_at"]),
            completed_at=_iso(r.get("completed_at")),
        )
        for r in rows
    ]
    return PlaybookRunHistoryResponse(runs=items, total=len(items))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _result_to_response(r: PlaybookRunResult) -> PlaybookRunResponse:
    return PlaybookRunResponse(
        playbook_name=r.playbook_name,
        topic_cluster=r.topic_cluster,
        triggered=r.triggered,
        dry_run=r.dry_run,
        cooldown_skipped=r.cooldown_skipped,
        actions=[
            ActionResultResponse(
                action_type=a.action_type,
                success=a.success,
                dry_run=a.dry_run,
                detail=a.detail,
                error=a.error,
            )
            for a in r.actions
        ],
        status=r.status,
        run_id=r.run_id,
    )


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)
