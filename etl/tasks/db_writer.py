"""DB writer — batch-inserts enriched signals into PostgreSQL.

Uses ON CONFLICT DO NOTHING as a safety net against duplicates that slip past
the deduplicator (e.g., two DAG runs in flight simultaneously).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

_INSERT_SQL = """
    INSERT INTO enriched_signals (
        event_id, source, collected_at, enriched_at,
        category, confidence, topic_tags, sentiment, urgency,
        engagement_score, raw_text, url, reasoning
    )
    VALUES %s
    ON CONFLICT (event_id) DO NOTHING
"""


def write_enriched_signals(enriched_dicts: list[dict]) -> int:
    """Batch-insert enriched signal dicts into PostgreSQL.

    Args:
        enriched_dicts: List of dicts from classify_batch_sync (XCom-serialized).

    Returns:
        Number of rows submitted for insertion (duplicates silently ignored by DB).
    """
    if not enriched_dicts:
        return 0

    rows = [_to_row(d) for d in enriched_dicts]
    dsn = os.environ.get("POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage")

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, _INSERT_SQL, rows, page_size=100)
        conn.commit()

    logger.info("Submitted %d enriched signals to DB", len(rows))
    return len(rows)


# ── private ───────────────────────────────────────────────────────────────────


def _to_row(d: dict) -> tuple[Any, ...]:
    """Map an enriched signal dict to the DB column order defined in _INSERT_SQL."""
    collected_at = _ensure_tz(d.get("collected_at"))
    enriched_at = _ensure_tz(d.get("enriched_at")) or datetime.now(tz=timezone.utc)

    return (
        d["event_id"],
        d["source"],
        collected_at,
        enriched_at,
        d["category"],
        float(d["confidence"]),
        d.get("topic_tags", []),
        d["sentiment"],
        d["urgency"],
        float(d.get("engagement_score", 0.0)),
        d.get("raw_text", ""),
        d.get("url", ""),
        d.get("reasoning", ""),
    )


def _ensure_tz(value: Any) -> datetime | None:
    """Normalize to a timezone-aware datetime; accept str or datetime."""
    if value is None:
        return None
    if isinstance(value, str):
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None
