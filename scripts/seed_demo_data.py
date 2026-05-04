"""Seed synthetic enriched_signals and golden_records for dashboard demo.

The heatmap reads directly from enriched_signals (grouped by topic_tags[1] and
5-minute time buckets) so no mpi_history writes are needed.

Usage (from repo root):
    python scripts/seed_demo_data.py
"""

from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import psycopg2.extras

DSN = os.environ.get("POSTGRES_DSN", "postgresql://trend:trend@localhost:5433/trend_arbitrage")

# ── Cluster definitions ────────────────────────────────────────────────────────

CLUSTERS = [
    {
        "name": "ai-chips",
        "sources": ["reddit", "twitter", "news"],
        "positive_ratio": 0.75,
        "signal_count": 42,
        "urgency": "high",
    },
    {
        "name": "llm-regulation",
        "sources": ["news", "linkedin", "rss"],
        "positive_ratio": 0.25,
        "signal_count": 28,
        "urgency": "high",
    },
    {
        "name": "generative-ai-tools",
        "sources": ["reddit", "twitter", "rss"],
        "positive_ratio": 0.80,
        "signal_count": 35,
        "urgency": "medium",
    },
    {
        "name": "autonomous-vehicles",
        "sources": ["news", "twitter", "scraper"],
        "positive_ratio": 0.55,
        "signal_count": 18,
        "urgency": "medium",
    },
    {
        "name": "open-source-models",
        "sources": ["reddit", "rss", "twitter"],
        "positive_ratio": 0.70,
        "signal_count": 22,
        "urgency": "low",
    },
]

SAMPLE_TEXTS = {
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


def _bucket_time(minutes_ago: int) -> datetime:
    """Return a timestamp roughly `minutes_ago` minutes in the past with jitter."""
    jitter = random.randint(-90, 90)
    return datetime.now(tz=timezone.utc) - timedelta(seconds=minutes_ago * 60 + jitter)


def seed_signals(conn) -> None:
    with conn.cursor() as cur:
        for cluster in CLUSTERS:
            name = cluster["name"]
            n = cluster["signal_count"]
            texts = SAMPLE_TEXTS[name]

            for i in range(n):
                roll = random.random()
                if roll < cluster["positive_ratio"]:
                    sentiment, category = "positive", "opportunity"
                elif roll < cluster["positive_ratio"] + 0.15:
                    sentiment, category = "negative", "threat"
                else:
                    sentiment, category = "neutral", "noise"

                # Bias 1/3 of signals to the last 15 min → drives velocity score up
                minutes_ago = random.randint(0, 15) if i < n // 3 else random.randint(15, 60)

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
                        _bucket_time(minutes_ago),
                        category,
                        round(random.uniform(0.65, 0.97), 3),
                        [name],            # topic_tags[1] is what the heatmap groups by
                        sentiment,
                        cluster["urgency"],
                        round(random.uniform(50, 2000), 2),
                        texts[i % len(texts)],
                        f"https://example.com/{name}/{i}",
                        f"Synthetic demo signal for cluster '{name}'.",
                    ),
                )

            print(f"  ✓  {n:>3} signals → '{name}'")

    conn.commit()


def seed_golden_records(conn) -> None:
    threshold = float(os.environ.get("MPI_THRESHOLD", "0.72"))

    # Clusters with high positive_ratio and signal count will naturally exceed threshold;
    # hard-code plausible MPI scores consistent with the signal distribution.
    mpi_scores = {
        "ai-chips":           0.87,
        "generative-ai-tools": 0.81,
        "llm-regulation":     0.74,
        "autonomous-vehicles": 0.61,
        "open-source-models": 0.68,
    }

    with conn.cursor() as cur:
        for cluster in CLUSTERS:
            name = cluster["name"]
            mpi = mpi_scores[name]
            if mpi < threshold:
                print(f"  ·  MPI {mpi:.3f} below threshold for '{name}' — skipped")
                continue

            expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=4)
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
            print(f"  ✓  Golden Record created → '{name}' (MPI {mpi:.3f})")

    conn.commit()


def main() -> None:
    print(f"\nConnecting to …{DSN.split('@')[-1]}")
    conn = psycopg2.connect(DSN)
    psycopg2.extras.register_uuid()

    print("\n── Seeding enriched signals ─────────────────────────────────────────")
    seed_signals(conn)

    print("\n── Seeding golden records ───────────────────────────────────────────")
    seed_golden_records(conn)

    conn.close()
    print("\nDone — refresh the dashboard at http://localhost:3000\n")


if __name__ == "__main__":
    main()
