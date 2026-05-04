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
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import require_scope
from api.db import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])

# ── Cluster definitions ───────────────────────────────────────────────────────

_MPI_THRESHOLD = 0.72

_CLUSTERS = [
    {"name": "ai-chips",           "sources": ["reddit", "twitter", "news"],    "positive_ratio": 0.75, "signal_count": 42, "urgency": "high",   "mpi": 0.87},
    {"name": "llm-regulation",     "sources": ["news", "linkedin", "rss"],      "positive_ratio": 0.25, "signal_count": 28, "urgency": "high",   "mpi": 0.74},
    {"name": "generative-ai-tools","sources": ["reddit", "twitter", "rss"],     "positive_ratio": 0.80, "signal_count": 35, "urgency": "medium", "mpi": 0.81},
    {"name": "autonomous-vehicles","sources": ["news", "twitter", "scraper"],   "positive_ratio": 0.55, "signal_count": 18, "urgency": "medium", "mpi": 0.61},
    {"name": "open-source-models", "sources": ["reddit", "rss", "twitter"],     "positive_ratio": 0.70, "signal_count": 22, "urgency": "low",    "mpi": 0.68},
]

_SAMPLE_TEXTS: dict[str, list[str]] = {
    "ai-chips": [
        "NVIDIA H100 allocation waitlists extending to Q3 — major cloud providers reporting shortages",
        "AMD MI300X gaining traction as H100 alternative, 40% cost reduction for inference workloads",
        "GPU prices surging on secondary market, up 35% month-over-month for data center GPUs",
        "TSMC expanding 3nm capacity, primary beneficiary expected to be AI chip manufacturers",
        "Intel Gaudi 3 benchmarks released — competitive on transformer training at lower price point",
    ],
    "llm-regulation": [
        "EU AI Act enforcement timeline confirmed — high-risk AI systems face compliance deadline",
        "FTC opens inquiry into foundation model market concentration and competitive effects",
        "California AI safety bill introduced with mandatory testing requirements for frontier models",
        "OpenAI, Anthropic, Google sign voluntary White House AI safety commitments",
        "China releases updated generative AI regulations requiring content moderation at scale",
    ],
    "generative-ai-tools": [
        "Claude 4 adoption accelerating in enterprise — coding assistant market share growing",
        "Adobe Firefly integration into Creative Cloud drives 60% increase in AI image generation",
        "GitHub Copilot Enterprise reaches 1M paid seats, Microsoft reports in quarterly earnings",
        "Midjourney v7 benchmarks show photorealism improvements over Stable Diffusion 3",
        "GPT-5 rumors circulating after OpenAI infrastructure job postings spike 200%",
    ],
    "autonomous-vehicles": [
        "Waymo expanding robotaxi service to 10 new cities by end of year",
        "Tesla FSD v13 rollout shows 40% reduction in interventions per mile in beta",
        "Uber partners with Waymo for autonomous ride-hailing in San Francisco and Phoenix",
        "NHTSA proposes updated autonomous vehicle testing framework, comment period open",
        "Cruise resumes limited operations after safety review with new geofencing restrictions",
    ],
    "open-source-models": [
        "Meta Llama 3.2 outperforms GPT-4o on coding benchmarks, available commercially",
        "Mistral Large 2 reaches top-5 on LMSYS Chatbot Arena leaderboard",
        "HuggingFace reports 50% of enterprise AI projects now use open-source base models",
        "Microsoft releases Phi-3.5 mini with 128K context, designed for edge deployment",
        "Google opens Gemma 2 weights for commercial use under Apache 2.0 license",
    ],
}


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
def seed_demo(
    _subject: str = Depends(require_scope("write:alerts")),
) -> SeedResponse:
    """Insert synthetic enriched_signals for 5 clusters and create golden records."""
    now = datetime.now(tz=timezone.utc)
    cluster_results: list[ClusterResult] = []
    total_signals = 0
    total_golden = 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            for cluster in _CLUSTERS:
                name = cluster["name"]
                n = cluster["signal_count"]
                texts = _SAMPLE_TEXTS[name]

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
def reset_demo(
    _subject: str = Depends(require_scope("write:alerts")),
) -> ResetResponse:
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
