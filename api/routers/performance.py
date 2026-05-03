"""Performance router — feedback loop metrics and calibration proposals.

GET  /performance/summary          — Golden Record hit rate, CTR lift by cluster,
                                     pending calibration proposals.
POST /performance/apply-proposal/{id} — Apply a pending calibration proposal:
                                     writes proposed source_weights to
                                     config/source_weights.json (takes effect on
                                     next MPI computation cycle) and marks the
                                     proposal as applied.
                                     The proposed MPI_THRESHOLD is returned but
                                     must be set manually as the MPI_THRESHOLD
                                     environment variable — no auto-apply.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_scope
from api.db import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["performance"])

_WEIGHTS_PATH = Path(os.environ.get("SOURCE_WEIGHTS_PATH", "config/source_weights.json"))
_POSITIVE_CTR_THRESHOLD: float = float(os.environ.get("POSITIVE_CTR_THRESHOLD", "0.015"))


# ── Response models ───────────────────────────────────────────────────────────


class ClusterPerformance(BaseModel):
    topic_cluster: str
    avg_ctr: float
    hit_count: int
    total_count: int


class PendingProposal(BaseModel):
    id: str
    proposed_mpi_threshold: float
    precision: float
    recall: float
    sample_count: int
    proposed_at: str


class PerformanceSummary(BaseModel):
    hit_rate: float
    total_measured: int
    total_hits: int
    avg_ctr_by_cluster: list[ClusterPerformance]
    pending_proposals: list[PendingProposal]


class ApplyProposalResponse(BaseModel):
    proposal_id: str
    status: str
    proposed_mpi_threshold: float
    source_weights_applied: dict[str, float]
    note: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/summary", response_model=PerformanceSummary)
def get_performance_summary(
    _subject: str = Depends(require_scope("read:segments")),
) -> PerformanceSummary:
    """Return Golden Record hit rate, per-cluster CTR, and pending proposals."""
    with get_conn() as conn:
        outcomes = _load_outcomes(conn)
        cluster_stats = _load_cluster_stats(conn)
        proposals = _load_pending_proposals(conn)

    total_measured = len(outcomes)
    total_hits = sum(1 for row in outcomes if row["ctr"] >= _POSITIVE_CTR_THRESHOLD)
    hit_rate = total_hits / total_measured if total_measured else 0.0

    return PerformanceSummary(
        hit_rate=round(hit_rate, 4),
        total_measured=total_measured,
        total_hits=total_hits,
        avg_ctr_by_cluster=[
            ClusterPerformance(
                topic_cluster=r["topic_cluster"],
                avg_ctr=round(float(r["avg_ctr"]), 4),
                hit_count=int(r["hit_count"]),
                total_count=int(r["total_count"]),
            )
            for r in cluster_stats
        ],
        pending_proposals=[
            PendingProposal(
                id=p["id"],
                proposed_mpi_threshold=float(p["proposed_mpi_threshold"]),
                precision=float(p["precision"]),
                recall=float(p["recall"]),
                sample_count=int(p["sample_count"]),
                proposed_at=_iso(p["proposed_at"]),
            )
            for p in proposals
        ],
    )


@router.post("/apply-proposal/{proposal_id}", response_model=ApplyProposalResponse)
def apply_proposal(
    proposal_id: str,
    _subject: str = Depends(require_scope("write:alerts")),
) -> ApplyProposalResponse:
    """Apply a pending calibration proposal.

    Writes proposed_source_weights to config/source_weights.json.
    The proposed MPI_THRESHOLD is returned in the response body — it must be
    applied manually as the MPI_THRESHOLD environment variable.

    Marks the proposal as 'applied' in the database.
    """
    with get_conn() as conn:
        proposal = _load_proposal(conn, proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail=f"Proposal {proposal_id!r} not found")

        if proposal["status"] != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Proposal {proposal_id!r} is already '{proposal['status']}'",
            )

        weights: dict[str, float] = proposal["proposed_source_weights"]
        proposed_threshold = float(proposal["proposed_mpi_threshold"])

        # Write source weights to disk — takes effect on next MPI computation cycle
        _write_source_weights(weights)

        # Mark proposal as applied
        _mark_proposal(conn, proposal_id, "applied")
        conn.commit()

    logger.info(
        "Calibration proposal %s applied: threshold=%.3f weights=%s",
        proposal_id,
        proposed_threshold,
        weights,
    )

    return ApplyProposalResponse(
        proposal_id=proposal_id,
        status="applied",
        proposed_mpi_threshold=proposed_threshold,
        source_weights_applied=weights,
        note=(
            f"Source weights written to {_WEIGHTS_PATH} and will take effect on the next "
            f"MPI computation cycle. To apply the proposed MPI threshold ({proposed_threshold}), "
            "set MPI_THRESHOLD in your environment and restart the pipeline."
        ),
    )


# ── DB helpers ────────────────────────────────────────────────────────────────


def _load_outcomes(conn) -> list[dict]:
    """Return the most recent CTR measurement per Golden Record."""
    sql = """
        SELECT DISTINCT ON (pe.golden_record_id)
            pe.golden_record_id::text,
            pe.value AS ctr
        FROM performance_events pe
        WHERE pe.metric = 'ctr'
        ORDER BY pe.golden_record_id, pe.measured_at DESC
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]


def _load_cluster_stats(conn) -> list[dict]:
    """Return avg CTR and hit/total count per topic cluster."""
    sql = """
        SELECT gr.topic_cluster,
               AVG(pe.value)                                      AS avg_ctr,
               SUM(CASE WHEN pe.value >= %s THEN 1 ELSE 0 END)   AS hit_count,
               COUNT(*)                                           AS total_count
        FROM performance_events pe
        JOIN golden_records gr ON gr.id = pe.golden_record_id
        WHERE pe.metric = 'ctr'
        GROUP BY gr.topic_cluster
        ORDER BY avg_ctr DESC
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (_POSITIVE_CTR_THRESHOLD,))
        return [dict(r) for r in cur.fetchall()]


def _load_pending_proposals(conn) -> list[dict]:
    sql = """
        SELECT id::text, proposed_mpi_threshold, precision, recall,
               sample_count, proposed_at
        FROM calibration_proposals
        WHERE status = 'pending'
        ORDER BY proposed_at DESC
        LIMIT 10
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]


def _load_proposal(conn, proposal_id: str) -> dict | None:
    sql = """
        SELECT id::text, proposed_mpi_threshold, proposed_source_weights,
               precision, recall, sample_count, status
        FROM calibration_proposals
        WHERE id = %s::uuid
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (proposal_id,))
        row = cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    # psycopg2 may return JSONB as a string or already parsed
    weights = d["proposed_source_weights"]
    if isinstance(weights, str):
        weights = json.loads(weights)
    d["proposed_source_weights"] = {k: float(v) for k, v in weights.items()}
    return d


def _mark_proposal(conn, proposal_id: str, status: str) -> None:
    sql = """
        UPDATE calibration_proposals
        SET status = %s, reviewed_at = NOW()
        WHERE id = %s::uuid
    """
    with conn.cursor() as cur:
        cur.execute(sql, (status, proposal_id))


# ── File helpers ──────────────────────────────────────────────────────────────


def _write_source_weights(weights: dict[str, float]) -> None:
    """Overwrite config/source_weights.json with new weights.

    Preserves the _comment key if present; atomic write via a temp path.
    """
    existing: dict[str, Any] = {}
    if _WEIGHTS_PATH.exists():
        try:
            with _WEIGHTS_PATH.open(encoding="utf-8") as fh:
                existing = json.load(fh)
        except Exception:  # noqa: BLE001
            pass

    # Merge: keep _comment and unknown keys, overwrite known source weights
    merged: dict[str, Any] = {k: v for k, v in existing.items() if k.startswith("_")}
    merged.update(weights)

    _WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _WEIGHTS_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
    tmp.replace(_WEIGHTS_PATH)
    logger.info("source_weights.json updated: %s", weights)


# ── Misc helpers ──────────────────────────────────────────────────────────────


def _iso(value: datetime | str | None) -> str:
    if value is None:
        return ""
    return value.isoformat() if isinstance(value, datetime) else str(value)
