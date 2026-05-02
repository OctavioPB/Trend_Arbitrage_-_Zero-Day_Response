"""Playbook engine — evaluates trigger conditions and executes action steps.

Design decisions:
  - load_playbooks() re-reads config/playbooks.json on every call so changes
    take effect without a service restart (acceptance criterion).
  - Actions are dispatched by type string via _ACTION_REGISTRY. Unknown types
    produce a no-op result rather than crashing.
  - Cooldown is enforced by querying playbook_runs for recent successful runs
    for the same (playbook_name, topic_cluster) pair.
  - dry_run=True runs the full evaluation and action dispatch but does NOT
    call external APIs and does NOT write a permanent DB row (persists with
    dry_run=True so the history endpoint still shows test runs).
  - A failure in one action step is logged but does NOT block subsequent steps.
"""

from __future__ import annotations

import fnmatch
import importlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "playbooks.json")
_CONFIG_PATH_ENV = "PLAYBOOKS_CONFIG_PATH"

# Maps action type string → fully qualified module path
_ACTION_REGISTRY: dict[str, str] = {
    "bid_adjustment": "playbooks.actions.bid_adjustment",
    "content_brief": "playbooks.actions.content_brief",
    "slack_escalation": "playbooks.actions.slack_escalation",
}


# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass
class ActionResult:
    action_type: str
    success: bool
    dry_run: bool
    detail: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "success": self.success,
            "dry_run": self.dry_run,
            "detail": self.detail,
            "error": self.error,
        }


@dataclass
class PlaybookRunResult:
    playbook_name: str
    topic_cluster: str
    triggered: bool
    dry_run: bool
    cooldown_skipped: bool
    actions: list[ActionResult] = field(default_factory=list)
    status: str = "skipped"
    run_id: str | None = None


# ── Engine ─────────────────────────────────────────────────────────────────────


class PlaybookEngine:
    """Evaluate playbooks against a Golden Record and execute matching ones."""

    def __init__(
        self,
        config_path: str | None = None,
        dsn: str | None = None,
    ) -> None:
        self._config_path = config_path or os.environ.get(
            _CONFIG_PATH_ENV, _DEFAULT_CONFIG_PATH
        )
        self._dsn = dsn or os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )

    # ── Public ────────────────────────────────────────────────────────────────

    def load_playbooks(self) -> list[dict]:
        """Load the playbooks config from disk. Re-reads on every call."""
        try:
            with open(self._config_path, encoding="utf-8") as fh:
                data = json.load(fh)
            return [p for p in data if p.get("enabled", True)]
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Cannot load playbooks from %s: %s", self._config_path, exc)
            return []

    def run(
        self,
        golden_record: dict,
        dry_run: bool = False,
    ) -> list[PlaybookRunResult]:
        """Evaluate all enabled playbooks and execute those whose triggers match.

        Args:
            golden_record: Golden Record dict (must contain id, topic_cluster,
                           mpi_score, signal_count, audience_proxy, expires_at).
            dry_run:        If True, evaluate and dispatch actions without
                            calling external APIs; still persists the run row.

        Returns:
            One PlaybookRunResult per evaluated playbook.
        """
        playbooks = self.load_playbooks()
        results: list[PlaybookRunResult] = []

        record_id: str = golden_record.get("id", "")
        topic_cluster: str = golden_record.get("topic_cluster", "")

        try:
            conn = psycopg2.connect(self._dsn)
        except psycopg2.OperationalError as exc:
            logger.error("PlaybookEngine: cannot connect to DB: %s — skipping all playbooks", exc)
            return []

        try:
            for playbook in playbooks:
                result = self._run_one(conn, playbook, golden_record, record_id, topic_cluster, dry_run)
                results.append(result)
        finally:
            conn.close()

        return results

    # ── Private ───────────────────────────────────────────────────────────────

    def _run_one(
        self,
        conn,
        playbook: dict,
        golden_record: dict,
        record_id: str,
        topic_cluster: str,
        dry_run: bool,
    ) -> PlaybookRunResult:
        name: str = playbook.get("name", "unnamed")
        cooldown_minutes: int = int(playbook.get("cooldown_minutes", 60))
        trigger: dict = playbook.get("trigger") or {}

        result = PlaybookRunResult(
            playbook_name=name,
            topic_cluster=topic_cluster,
            triggered=False,
            dry_run=dry_run,
            cooldown_skipped=False,
            status="skipped",
        )

        if not self._matches_trigger(trigger, golden_record):
            return result

        result.triggered = True

        if not dry_run and self._is_in_cooldown(conn, name, topic_cluster, cooldown_minutes):
            result.cooldown_skipped = True
            logger.info(
                "Playbook %r in cooldown for cluster=%r — skipping", name, topic_cluster
            )
            return result

        action_configs: list[dict] = playbook.get("actions") or []
        result.actions = self._execute_actions(action_configs, golden_record, dry_run)
        result.status = _derive_status(result.actions)

        if record_id:
            result.run_id = self._persist_run(conn, record_id, result)

        return result

    def _matches_trigger(self, trigger: dict, record: dict) -> bool:
        """Return True if the golden record satisfies all trigger conditions."""
        min_mpi = float(trigger.get("min_mpi") or 0.0)
        if float(record.get("mpi_score") or 0.0) < min_mpi:
            return False

        pattern: str = trigger.get("topic_cluster_pattern") or "*"
        cluster: str = record.get("topic_cluster") or ""
        if not fnmatch.fnmatch(cluster, pattern):
            return False

        required_urgency = trigger.get("urgency")
        if required_urgency is not None:
            record_urgency = record.get("urgency") or ""
            allowed = (
                required_urgency
                if isinstance(required_urgency, list)
                else [required_urgency]
            )
            if record_urgency not in allowed:
                return False

        return True

    def _is_in_cooldown(
        self, conn, playbook_name: str, topic_cluster: str, cooldown_minutes: int
    ) -> bool:
        """Return True if this playbook fired successfully within the cooldown window."""
        sql = """
            SELECT id FROM playbook_runs
            WHERE playbook_name = %s
              AND topic_cluster = %s
              AND dry_run = false
              AND status IN ('success', 'partial')
              AND started_at > NOW() - (%s * INTERVAL '1 minute')
            LIMIT 1
        """
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (playbook_name, topic_cluster, cooldown_minutes))
                return cur.fetchone() is not None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cooldown check failed: %s — assuming not in cooldown", exc)
            return False

    def _execute_actions(
        self,
        action_configs: list[dict],
        golden_record: dict,
        dry_run: bool,
    ) -> list[ActionResult]:
        results: list[ActionResult] = []
        for cfg in action_configs:
            action_type: str = cfg.get("type", "")
            module_path = _ACTION_REGISTRY.get(action_type)

            if not module_path:
                logger.warning("Unknown action type %r — skipping", action_type)
                results.append(
                    ActionResult(
                        action_type=action_type or "unknown",
                        success=False,
                        dry_run=dry_run,
                        detail=f"Unknown action type: {action_type!r}",
                        error="not in registry",
                    )
                )
                continue

            try:
                module = importlib.import_module(module_path)
                raw = module.execute(cfg, golden_record, dry_run=dry_run)
                results.append(
                    ActionResult(
                        action_type=raw.get("type", action_type),
                        success=bool(raw.get("success")),
                        dry_run=bool(raw.get("dry_run")),
                        detail=raw.get("detail", ""),
                        error=raw.get("error"),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Action %r raised unexpectedly: %s", action_type, exc)
                results.append(
                    ActionResult(
                        action_type=action_type,
                        success=False,
                        dry_run=dry_run,
                        detail="Action raised an unexpected exception",
                        error=str(exc)[:200],
                    )
                )

        return results

    def _persist_run(self, conn, golden_record_id: str, result: PlaybookRunResult) -> str:
        """Write a playbook_runs row and return its id."""
        sql = """
            INSERT INTO playbook_runs
                (golden_record_id, playbook_name, topic_cluster,
                 actions_taken, dry_run, status, completed_at)
            VALUES (%s::uuid, %s, %s, %s, %s, %s, NOW())
            RETURNING id::text
        """
        actions_json = json.dumps([a.to_dict() for a in result.actions])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        golden_record_id,
                        result.playbook_name,
                        result.topic_cluster,
                        actions_json,
                        result.dry_run,
                        result.status,
                    ),
                )
                run_id: str = cur.fetchone()[0]
            conn.commit()
            return run_id
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist playbook run: %s", exc)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            return str(uuid.uuid4())  # synthetic id so the caller still gets a result


# ── Helpers ───────────────────────────────────────────────────────────────────


def _derive_status(actions: list[ActionResult]) -> str:
    if not actions:
        return "skipped"
    successes = sum(1 for a in actions if a.success)
    if successes == len(actions):
        return "success"
    if successes == 0:
        return "error"
    return "partial"
