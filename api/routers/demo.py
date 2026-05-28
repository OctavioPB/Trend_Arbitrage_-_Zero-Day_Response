"""Demo admin router — seed synthetic enriched_signals / golden_records, or reset.

POST   /demo/seed   — insert synthetic data for 5 clusters + create golden records
DELETE /demo/reset  — truncate enriched_signals and golden_records

Both endpoints require write:alerts scope (admin-only in the single-user setup).
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2.extras
from fastapi import APIRouter
from pydantic import BaseModel

from api.db import get_conn
from api.routers.clusters import DEFAULTS as _CLUSTER_DEFAULTS, ensure_table as _ensure_clusters

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])

_MPI_THRESHOLD = 0.72


def _load_clusters() -> list[dict]:
    """Return cluster configs from DB if any exist, otherwise fall back to defaults."""
    try:
        _ensure_clusters()
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM cluster_configs ORDER BY created_at ASC")
                rows = cur.fetchall()
        if rows:
            return [
                {
                    "name": r["name"],
                    "sources": list(r["sources"] or []),
                    "positive_ratio": float(r["positive_ratio"]),
                    "signal_count": int(r["signal_count"]),
                    "urgency": r["urgency"],
                    "mpi": float(r["mpi_score"]),
                    "sample_texts": list(r["sample_texts"] or []),
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Could not load cluster configs from DB, using defaults: %s", exc)
    return [
        {**c, "mpi": c["mpi_score"]}
        for c in _CLUSTER_DEFAULTS
    ]


# ── Response models ───────────────────────────────────────────────────────────


class ClusterResult(BaseModel):
    name: str
    signals_created: int
    mpi_score: float
    urgency: str
    golden_record_created: bool


class SeedResponse(BaseModel):
    seeded_at: datetime
    signals_total: int
    golden_records_total: int
    mpi_threshold: float
    clusters: list[ClusterResult]


class ResetResponse(BaseModel):
    reset_at: datetime
    signals_deleted: int
    golden_records_deleted: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/seed", response_model=SeedResponse)
def seed_demo() -> SeedResponse:
    """Insert synthetic enriched_signals for 5 clusters and create golden records."""
    now = datetime.now(tz=timezone.utc)
    cluster_results: list[ClusterResult] = []
    total_signals = 0
    total_golden = 0

    clusters = _load_clusters()

    with get_conn() as conn:
        with conn.cursor() as cur:
            for cluster in clusters:
                name = cluster["name"]
                n = cluster["signal_count"]
                texts = cluster.get("sample_texts") or [
                    f"Signal detected for topic cluster '{name}' — market activity increasing",
                    f"New development in '{name}' space attracting analyst attention",
                    f"Industry sources report momentum shift in '{name}' segment",
                ]

                for i in range(n):
                    roll = random.random()
                    if roll < cluster["positive_ratio"]:
                        sentiment, category = "positive", "opportunity"
                    elif roll < cluster["positive_ratio"] + 0.15:
                        sentiment, category = "negative", "threat"
                    else:
                        sentiment, category = "neutral", "noise"

                    # Bias 1/3 of signals to the last 15 min for higher velocity score
                    minutes_ago = random.randint(0, 15) if i < n // 3 else random.randint(15, 60)
                    jitter = random.randint(-90, 90)
                    collected_at = now - timedelta(seconds=minutes_ago * 60 + jitter)

                    cur.execute(
                        """
                        INSERT INTO enriched_signals
                            (event_id, source, collected_at, category, confidence,
                             topic_tags, sentiment, urgency, engagement_score,
                             raw_text, url, reasoning)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (event_id) DO NOTHING
                        """,
                        (
                            str(uuid.uuid4()),
                            random.choice(cluster["sources"]),
                            collected_at,
                            category,
                            round(random.uniform(0.65, 0.97), 3),
                            [name],
                            sentiment,
                            cluster["urgency"],
                            round(random.uniform(50, 2000), 2),
                            texts[i % len(texts)],
                            f"https://example.com/{name}/{i}",
                            f"Synthetic demo signal for cluster '{name}'.",
                        ),
                    )

                total_signals += n

                # Create golden record if MPI exceeds threshold
                mpi = cluster["mpi"]
                golden_created = False
                if mpi >= _MPI_THRESHOLD:
                    expires_at = now + timedelta(hours=4)
                    audience = {
                        "sources": cluster["sources"],
                        "topic_tags": [name],
                        "urgency": cluster["urgency"],
                    }
                    cur.execute(
                        """
                        INSERT INTO golden_records
                            (topic_cluster, mpi_score, signal_count,
                             audience_proxy, recommended_action, expires_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            name,
                            mpi,
                            cluster["signal_count"],
                            psycopg2.extras.Json(audience),
                            f"Launch targeted campaign on '{name}' — MPI {mpi:.3f} above threshold",
                            expires_at,
                        ),
                    )
                    golden_created = True
                    total_golden += 1

                cluster_results.append(
                    ClusterResult(
                        name=name,
                        signals_created=n,
                        mpi_score=mpi,
                        urgency=cluster["urgency"],
                        golden_record_created=golden_created,
                    )
                )

        conn.commit()

    logger.info("Demo seed completed: %d signals, %d golden records", total_signals, total_golden)

    return SeedResponse(
        seeded_at=now,
        signals_total=total_signals,
        golden_records_total=total_golden,
        mpi_threshold=_MPI_THRESHOLD,
        clusters=cluster_results,
    )


@router.delete("/reset", response_model=ResetResponse)
def reset_demo() -> ResetResponse:
    """Delete all rows from enriched_signals and golden_records."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM golden_records")
            golden_deleted = cur.rowcount

            cur.execute("DELETE FROM enriched_signals")
            signals_deleted = cur.rowcount

        conn.commit()

    logger.info("Demo reset: deleted %d signals, %d golden records", signals_deleted, golden_deleted)

    return ResetResponse(
        reset_at=datetime.now(tz=timezone.utc),
        signals_deleted=signals_deleted,
        golden_records_deleted=golden_deleted,
    )
