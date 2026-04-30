"""Alert rule management — DB operations for loading, creating, and deleting rules."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import psycopg2.extras
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_WILDCARD = "*"


class AlertRule(BaseModel):
    id: str
    topic_cluster: str  # '*' matches all clusters
    min_mpi: float
    min_signal_count: int
    suppression_minutes: int
    channels: list[dict[str, Any]]
    enabled: bool
    last_alerted_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ── Read ──────────────────────────────────────────────────────────────────────


def get_matching_rules(conn, topic_cluster: str, mpi_score: float) -> list[AlertRule]:
    """Return enabled rules that match topic and MPI score, respecting suppression window.

    Suppression is enforced in SQL: rules where last_alerted_at is still within
    the suppression window are excluded entirely, avoiding a Python-level check.
    """
    sql = """
        SELECT
            id::text, topic_cluster, min_mpi, min_signal_count,
            suppression_minutes, channels, enabled,
            last_alerted_at, created_at, updated_at
        FROM alert_rules
        WHERE enabled = true
          AND min_mpi <= %s
          AND (topic_cluster = %s OR topic_cluster = %s)
          AND (
              last_alerted_at IS NULL
              OR NOW() - last_alerted_at > (suppression_minutes * INTERVAL '1 minute')
          )
        ORDER BY min_mpi DESC
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (mpi_score, topic_cluster, _WILDCARD))
        rows = cur.fetchall()
    return [_row_to_rule(dict(r)) for r in rows]


def list_rules(conn) -> list[AlertRule]:
    sql = """
        SELECT
            id::text, topic_cluster, min_mpi, min_signal_count,
            suppression_minutes, channels, enabled,
            last_alerted_at, created_at, updated_at
        FROM alert_rules
        ORDER BY created_at DESC
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [_row_to_rule(dict(r)) for r in rows]


# ── Write ─────────────────────────────────────────────────────────────────────


def create_rule(conn, rule_data: dict) -> AlertRule:
    sql = """
        INSERT INTO alert_rules
            (topic_cluster, min_mpi, min_signal_count, suppression_minutes, channels, enabled)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING
            id::text, topic_cluster, min_mpi, min_signal_count,
            suppression_minutes, channels, enabled,
            last_alerted_at, created_at, updated_at
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            sql,
            (
                rule_data.get("topic_cluster", _WILDCARD),
                rule_data["min_mpi"],
                rule_data.get("min_signal_count", 1),
                rule_data.get("suppression_minutes", 30),
                json.dumps(rule_data.get("channels", [])),
                rule_data.get("enabled", True),
            ),
        )
        row = dict(cur.fetchone())
    conn.commit()
    return _row_to_rule(row)


def delete_rule(conn, rule_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM alert_rules WHERE id = %s::uuid RETURNING id",
            (rule_id,),
        )
        deleted = cur.fetchone() is not None
    conn.commit()
    return deleted


def update_last_alerted(conn, rule_id: str) -> None:
    """Stamp the suppression clock for a rule after a successful alert dispatch."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE alert_rules SET last_alerted_at = NOW() WHERE id = %s::uuid",
            (rule_id,),
        )
    conn.commit()


# ── Internal ──────────────────────────────────────────────────────────────────


def _row_to_rule(row: dict) -> AlertRule:
    channels = row.get("channels") or []
    if isinstance(channels, str):
        channels = json.loads(channels)
    return AlertRule(
        id=row["id"],
        topic_cluster=row["topic_cluster"],
        min_mpi=float(row["min_mpi"] or 0.0),
        min_signal_count=int(row["min_signal_count"] or 1),
        suppression_minutes=int(row["suppression_minutes"] or 30),
        channels=channels,
        enabled=bool(row["enabled"]),
        last_alerted_at=row.get("last_alerted_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
