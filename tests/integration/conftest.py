"""Fixtures for integration tests.

Tests require Docker services running:
    docker-compose up -d
    alembic upgrade head

If PostgreSQL is not reachable, all integration tests are skipped.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import psycopg2
import pytest

_DSN = os.environ.get(
    "POSTGRES_DSN",
    "postgresql://trend:trend@localhost:5432/trend_arbitrage",
)


def _db_reachable() -> bool:
    try:
        conn = psycopg2.connect(_DSN, connect_timeout=3)
        conn.close()
        return True
    except psycopg2.OperationalError:
        return False


@pytest.fixture(scope="session")
def db_conn():
    """Session-scoped raw DB connection. Skips the session if DB is unreachable."""
    if not _db_reachable():
        pytest.skip("PostgreSQL not available — run 'docker-compose up -d' first")
    conn = psycopg2.connect(_DSN)
    conn.autocommit = False
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def seeded_signals(db_conn):
    """Insert test enriched signals and clean them up after the module."""
    now = datetime.now(tz=timezone.utc)
    test_ids = []

    rows = [
        (
            str(uuid.uuid4()),               # event_id
            "reddit",                         # source
            now,                              # collected_at
            "opportunity",                    # category
            0.87,                             # confidence
            ["ai-investment", "vc-funding"],  # topic_tags
            "positive",                       # sentiment
            "high",                           # urgency
            500.0,                            # engagement_score
            "https://reddit.com/r/stocks/comments/abc/test",  # url
            "Strong demand signal for AI investments.",        # reasoning
        ),
        (
            str(uuid.uuid4()),
            "twitter",
            now,
            "threat",
            0.72,
            ["competitor-pricing"],
            "negative",
            "medium",
            120.0,
            "https://twitter.com/i/web/status/123",
            "Competitor announced lower pricing tier.",
        ),
        (
            str(uuid.uuid4()),
            "scraper",
            now,
            "noise",
            0.35,
            [],
            "neutral",
            "low",
            0.0,
            "https://techcrunch.com/article/generic",
            "No actionable signal detected.",
        ),
    ]

    insert_sql = """
        INSERT INTO enriched_signals
            (event_id, source, collected_at, category, confidence, topic_tags,
             sentiment, urgency, engagement_score, url, reasoning)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id::text
    """
    with db_conn.cursor() as cur:
        for row in rows:
            cur.execute(insert_sql, row)
            test_ids.append(cur.fetchone()[0])
    db_conn.commit()

    yield test_ids

    # Cleanup
    with db_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM enriched_signals WHERE id = ANY(%s::uuid[])",
            (test_ids,),
        )
    db_conn.commit()


@pytest.fixture(scope="module")
def seeded_golden_record(db_conn):
    """Insert a test golden record and clean it up after the module."""
    from datetime import timedelta

    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=4)

    insert_sql = """
        INSERT INTO golden_records
            (topic_cluster, mpi_score, signal_count, audience_proxy,
             recommended_action, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id::text
    """
    with db_conn.cursor() as cur:
        cur.execute(
            insert_sql,
            (
                "ai-investment",
                0.85,
                12,
                json.dumps({"subreddits": ["r/stocks"], "top_topics": ["ai-investment"]}),
                "Prepare segment for AI investment keywords.",
                expires_at,
            ),
        )
        record_id = cur.fetchone()[0]
    db_conn.commit()

    yield record_id

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM golden_records WHERE id = %s::uuid", (record_id,))
    db_conn.commit()
