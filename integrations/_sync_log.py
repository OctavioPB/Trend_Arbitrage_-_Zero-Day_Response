"""Helpers for reading and writing audience_sync_log rows.

These functions accept a live psycopg2 connection (not a DSN string) so the
DAG task can manage transaction boundaries explicitly. Never call conn.commit()
inside these helpers — the caller decides when to commit.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def already_synced(conn, golden_record_id: str, platform: str) -> bool:
    """Return True if a *successful* sync already exists for this record + platform."""
    sql = """
        SELECT id FROM audience_sync_log
        WHERE golden_record_id = %s::uuid
          AND platform = %s
          AND status = 'success'
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (golden_record_id, platform))
        return cur.fetchone() is not None


def write_sync_log(
    conn,
    golden_record_id: str,
    platform: str,
    status: str,
    *,
    audience_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Upsert a row in audience_sync_log.

    ON CONFLICT DO UPDATE means a retry attempt overwrites the previous error row.
    Caller must commit the transaction after calling this function.
    """
    sql = """
        INSERT INTO audience_sync_log
            (golden_record_id, platform, status, audience_id, synced_at, error_message)
        VALUES (%s::uuid, %s, %s, %s, NOW(), %s)
        ON CONFLICT (golden_record_id, platform) DO UPDATE
            SET status        = EXCLUDED.status,
                audience_id   = EXCLUDED.audience_id,
                synced_at     = NOW(),
                error_message = EXCLUDED.error_message
    """
    # Truncate error messages — never log raw exception text that may contain credentials
    safe_error = _truncate(error_message, 500) if error_message else None

    with conn.cursor() as cur:
        cur.execute(sql, (golden_record_id, platform, status, audience_id, safe_error))

    logger.info(
        "audience_sync_log upserted: golden_record_id=%s platform=%s status=%s",
        golden_record_id,
        platform,
        status,
    )


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] if len(text) > max_len else text
