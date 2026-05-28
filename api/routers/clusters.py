"""Cluster configuration router — personalize the topic clusters used for
signal ingestion and demo seeding.

GET    /clusters          — list all saved cluster configs
POST   /clusters          — create a new cluster
PUT    /clusters/{name}   — update an existing cluster
DELETE /clusters/{name}   — delete a cluster
POST   /clusters/reset    — restore the five built-in defaults
"""

from __future__ import annotations

import logging
from datetime import datetime

import psycopg2.extras
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.db import get_conn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clusters", tags=["clusters"])

VALID_SOURCES = {"reddit", "twitter", "news", "linkedin", "rss", "scraper"}
VALID_URGENCY = {"low", "medium", "high"}

# ── Built-in defaults (also used by demo seeding when no custom configs exist) ─

DEFAULTS: list[dict] = [
    {
        "name": "ai-chips",
        "display_name": "AI Chips",
        "sources": ["reddit", "twitter", "news"],
        "urgency": "high",
        "positive_ratio": 0.75,
        "signal_count": 42,
        "mpi_score": 0.87,
        "sample_texts": [
            "NVIDIA H100 allocation waitlists extending to Q3 — major cloud providers reporting shortages",
            "AMD MI300X gaining traction as H100 alternative, 40% cost reduction for inference workloads",
            "GPU prices surging on secondary market, up 35% month-over-month for data center GPUs",
            "TSMC expanding 3nm capacity, primary beneficiary expected to be AI chip manufacturers",
            "Intel Gaudi 3 benchmarks released — competitive on transformer training at lower price point",
        ],
    },
    {
        "name": "llm-regulation",
        "display_name": "LLM Regulation",
        "sources": ["news", "linkedin", "rss"],
        "urgency": "high",
        "positive_ratio": 0.25,
        "signal_count": 28,
        "mpi_score": 0.74,
        "sample_texts": [
            "EU AI Act enforcement timeline confirmed — high-risk AI systems face compliance deadline",
            "FTC opens inquiry into foundation model market concentration and competitive effects",
            "California AI safety bill introduced with mandatory testing requirements for frontier models",
            "OpenAI, Anthropic, Google sign voluntary White House AI safety commitments",
            "China releases updated generative AI regulations requiring content moderation at scale",
        ],
    },
    {
        "name": "generative-ai-tools",
        "display_name": "Generative AI Tools",
        "sources": ["reddit", "twitter", "rss"],
        "urgency": "medium",
        "positive_ratio": 0.80,
        "signal_count": 35,
        "mpi_score": 0.81,
        "sample_texts": [
            "Claude 4 adoption accelerating in enterprise — coding assistant market share growing",
            "Adobe Firefly integration into Creative Cloud drives 60% increase in AI image generation",
            "GitHub Copilot Enterprise reaches 1M paid seats, Microsoft reports in quarterly earnings",
            "Midjourney v7 benchmarks show photorealism improvements over Stable Diffusion 3",
            "GPT-5 rumors circulating after OpenAI infrastructure job postings spike 200%",
        ],
    },
    {
        "name": "autonomous-vehicles",
        "display_name": "Autonomous Vehicles",
        "sources": ["news", "twitter", "scraper"],
        "urgency": "medium",
        "positive_ratio": 0.55,
        "signal_count": 18,
        "mpi_score": 0.61,
        "sample_texts": [
            "Waymo expanding robotaxi service to 10 new cities by end of year",
            "Tesla FSD v13 rollout shows 40% reduction in interventions per mile in beta",
            "Uber partners with Waymo for autonomous ride-hailing in San Francisco and Phoenix",
            "NHTSA proposes updated autonomous vehicle testing framework, comment period open",
            "Cruise resumes limited operations after safety review with new geofencing restrictions",
        ],
    },
    {
        "name": "open-source-models",
        "display_name": "Open-Source Models",
        "sources": ["reddit", "rss", "twitter"],
        "urgency": "low",
        "positive_ratio": 0.70,
        "signal_count": 22,
        "mpi_score": 0.68,
        "sample_texts": [
            "Meta Llama 3.2 outperforms GPT-4o on coding benchmarks, available commercially",
            "Mistral Large 2 reaches top-5 on LMSYS Chatbot Arena leaderboard",
            "HuggingFace reports 50% of enterprise AI projects now use open-source base models",
            "Microsoft releases Phi-3.5 mini with 128K context, designed for edge deployment",
            "Google opens Gemma 2 weights for commercial use under Apache 2.0 license",
        ],
    },
]

# ── Table bootstrap ───────────────────────────────────────────────────────────

def ensure_table() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cluster_configs (
                    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name           TEXT NOT NULL UNIQUE,
                    display_name   TEXT NOT NULL,
                    sources        TEXT[] NOT NULL DEFAULT '{}',
                    urgency        TEXT NOT NULL DEFAULT 'medium',
                    positive_ratio NUMERIC(4,3) NOT NULL DEFAULT 0.6,
                    signal_count   INT NOT NULL DEFAULT 20,
                    mpi_score      NUMERIC(4,3) NOT NULL DEFAULT 0.65,
                    sample_texts   JSONB NOT NULL DEFAULT '[]',
                    created_at     TIMESTAMPTZ DEFAULT NOW(),
                    updated_at     TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        conn.commit()

# ── Models ────────────────────────────────────────────────────────────────────

class ClusterIn(BaseModel):
    name: str = Field(..., pattern=r"^[a-z0-9][a-z0-9\-]*$")
    display_name: str = Field(..., min_length=1)
    sources: list[str] = Field(..., min_length=1)
    urgency: str
    positive_ratio: float = Field(..., ge=0.0, le=1.0)
    signal_count: int = Field(..., ge=1, le=200)
    mpi_score: float = Field(..., ge=0.0, le=1.0)
    sample_texts: list[str] = []


class ClusterOut(ClusterIn):
    id: str
    created_at: datetime
    updated_at: datetime


class ClusterListOut(BaseModel):
    clusters: list[ClusterOut]
    total: int

# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate(body: ClusterIn) -> None:
    bad = [s for s in body.sources if s not in VALID_SOURCES]
    if bad:
        raise HTTPException(422, f"Invalid sources: {bad}. Valid: {sorted(VALID_SOURCES)}")
    if body.urgency not in VALID_URGENCY:
        raise HTTPException(422, f"urgency must be one of {sorted(VALID_URGENCY)}")


def _to_out(row: dict) -> ClusterOut:
    return ClusterOut(
        id=str(row["id"]),
        name=row["name"],
        display_name=row["display_name"],
        sources=list(row["sources"] or []),
        urgency=row["urgency"],
        positive_ratio=float(row["positive_ratio"]),
        signal_count=int(row["signal_count"]),
        mpi_score=float(row["mpi_score"]),
        sample_texts=list(row["sample_texts"] or []),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=ClusterListOut)
def list_clusters() -> ClusterListOut:
    ensure_table()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM cluster_configs ORDER BY created_at ASC")
            rows = [dict(r) for r in cur.fetchall()]
    return ClusterListOut(clusters=[_to_out(r) for r in rows], total=len(rows))


@router.post("", response_model=ClusterOut, status_code=201)
def create_cluster(body: ClusterIn) -> ClusterOut:
    ensure_table()
    _validate(body)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO cluster_configs
                        (name, display_name, sources, urgency,
                         positive_ratio, signal_count, mpi_score, sample_texts)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (body.name, body.display_name, body.sources, body.urgency,
                     body.positive_ratio, body.signal_count, body.mpi_score,
                     psycopg2.extras.Json(body.sample_texts)),
                )
                row = dict(cur.fetchone())
            except psycopg2.errors.UniqueViolation:
                raise HTTPException(409, f"Cluster '{body.name}' already exists")
        conn.commit()
    logger.info("Cluster created: %s", body.name)
    return _to_out(row)


@router.put("/{name}", response_model=ClusterOut)
def update_cluster(name: str, body: ClusterIn) -> ClusterOut:
    ensure_table()
    _validate(body)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE cluster_configs SET
                    display_name   = %s,
                    sources        = %s,
                    urgency        = %s,
                    positive_ratio = %s,
                    signal_count   = %s,
                    mpi_score      = %s,
                    sample_texts   = %s,
                    updated_at     = NOW()
                WHERE name = %s
                RETURNING *
                """,
                (body.display_name, body.sources, body.urgency,
                 body.positive_ratio, body.signal_count, body.mpi_score,
                 psycopg2.extras.Json(body.sample_texts), name),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, f"Cluster '{name}' not found")
    logger.info("Cluster updated: %s", name)
    return _to_out(dict(row))


@router.delete("/{name}", status_code=204, response_model=None)
def delete_cluster(name: str) -> None:
    ensure_table()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cluster_configs WHERE name = %s RETURNING name", (name,))
            found = cur.fetchone() is not None
        conn.commit()
    if not found:
        raise HTTPException(404, f"Cluster '{name}' not found")
    logger.info("Cluster deleted: %s", name)


@router.post("/reset", response_model=ClusterListOut)
def reset_clusters() -> ClusterListOut:
    """Wipe all custom configs and restore the five built-in defaults."""
    ensure_table()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("DELETE FROM cluster_configs")
            for c in DEFAULTS:
                cur.execute(
                    """
                    INSERT INTO cluster_configs
                        (name, display_name, sources, urgency,
                         positive_ratio, signal_count, mpi_score, sample_texts)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (c["name"], c["display_name"], c["sources"], c["urgency"],
                     c["positive_ratio"], c["signal_count"], c["mpi_score"],
                     psycopg2.extras.Json(c["sample_texts"])),
                )
            cur.execute("SELECT * FROM cluster_configs ORDER BY created_at ASC")
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    logger.info("Cluster configs reset to defaults")
    return ClusterListOut(clusters=[_to_out(r) for r in rows], total=len(rows))
