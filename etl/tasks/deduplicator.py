"""Deduplicator — filters raw events whose event_id already exists in enriched_signals."""

import logging
import os

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def filter_new_events(events: list[dict]) -> list[dict]:
    """Return only events whose event_id is not yet in the enriched_signals table.

    Uses a single batch query rather than one query per event.
    """
    if not events:
        return []

    event_ids = [e["event_id"] for e in events]
    existing = _query_existing_ids(event_ids)

    new_events = [e for e in events if e["event_id"] not in existing]

    duplicates = len(events) - len(new_events)
    if duplicates:
        logger.info(
            "Deduplicated %d/%d events (%d already in DB)",
            len(new_events),
            len(events),
            duplicates,
        )

    return new_events


def _query_existing_ids(event_ids: list[str]) -> set[str]:
    dsn = os.environ.get("POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage")
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_id::text FROM enriched_signals WHERE event_id = ANY(%s)",
                    (event_ids,),
                )
                rows = cur.fetchall()
        return {row[0] for row in rows}
    except psycopg2.OperationalError as exc:
        logger.error("DB unavailable during dedup check — skipping dedup: %s", exc)
        return set()
