"""Unit tests for playbooks.engine and playbooks.actions.

All DB access and external HTTP calls are mocked. These tests never hit
the network or database.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, call, patch

import psycopg2
import pytest

from playbooks.engine import (
    ActionResult,
    PlaybookEngine,
    PlaybookRunResult,
    _derive_status,
)


# ── Fixtures & helpers ────────────────────────────────────────────────────────


def _make_record(**overrides) -> dict:
    base = dict(
        id="gr-001",
        topic_cluster="ai-chips",
        mpi_score=0.88,
        signal_count=20,
        urgency="high",
        audience_proxy={"subreddits": ["r/ML"], "top_topics": ["GPU"]},
        recommended_action="Activate campaigns",
        expires_at="2026-05-02T16:00:00+00:00",
    )
    base.update(overrides)
    return base


def _mock_conn_no_cooldown() -> MagicMock:
    """Return a mock psycopg2 connection whose cursor always returns no rows.

    This makes _is_in_cooldown return False so playbooks proceed normally,
    and makes _persist_run return a fake run id.
    """
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    # fetchone() returns None → not in cooldown; returns ("run-id",) for persist
    cur.fetchone.side_effect = [None, ("fake-run-id",)]
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def _make_engine(playbooks_data: list[dict] | None = None) -> PlaybookEngine:
    """Return an engine with a temp config file."""
    data = playbooks_data if playbooks_data is not None else _DEFAULT_PLAYBOOKS
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(data, fh)
        path = fh.name
    return PlaybookEngine(config_path=path, dsn="postgresql://unused/unused")


_DEFAULT_PLAYBOOKS = [
    {
        "name": "high-confidence",
        "description": "MPI >= 0.85",
        "enabled": True,
        "trigger": {"min_mpi": 0.85, "topic_cluster_pattern": "*", "urgency": None},
        "cooldown_minutes": 60,
        "actions": [{"type": "content_brief"}, {"type": "slack_escalation"}],
    }
]


# ── load_playbooks ────────────────────────────────────────────────────────────


class TestLoadPlaybooks:
    def test_returns_enabled_playbooks(self):
        engine = _make_engine(_DEFAULT_PLAYBOOKS)
        result = engine.load_playbooks()
        assert len(result) == 1
        assert result[0]["name"] == "high-confidence"

    def test_disabled_playbooks_are_excluded(self):
        data = [dict(_DEFAULT_PLAYBOOKS[0], enabled=False)]
        engine = _make_engine(data)
        assert engine.load_playbooks() == []

    def test_missing_file_returns_empty_list(self):
        engine = PlaybookEngine(config_path="/nonexistent/path.json", dsn="unused")
        assert engine.load_playbooks() == []

    def test_malformed_json_returns_empty_list(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("{not valid json}")
            path = fh.name
        engine = PlaybookEngine(config_path=path, dsn="unused")
        assert engine.load_playbooks() == []

    def test_reload_reflects_file_change(self):
        data = list(_DEFAULT_PLAYBOOKS)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(data, fh)
            path = fh.name
        engine = PlaybookEngine(config_path=path, dsn="unused")
        assert len(engine.load_playbooks()) == 1

        with open(path, "w", encoding="utf-8") as fh:
            json.dump([], fh)
        assert engine.load_playbooks() == []


# ── _matches_trigger ──────────────────────────────────────────────────────────


class TestMatchesTrigger:
    def _engine(self):
        return _make_engine()

    def test_matching_record_returns_true(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.85, "topic_cluster_pattern": "*", "urgency": None}
        assert engine._matches_trigger(trigger, _make_record(mpi_score=0.88)) is True

    def test_below_min_mpi_returns_false(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.9, "topic_cluster_pattern": "*", "urgency": None}
        assert engine._matches_trigger(trigger, _make_record(mpi_score=0.88)) is False

    def test_exact_min_mpi_matches(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.88, "topic_cluster_pattern": "*", "urgency": None}
        assert engine._matches_trigger(trigger, _make_record(mpi_score=0.88)) is True

    def test_wildcard_pattern_matches_any_cluster(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.0, "topic_cluster_pattern": "*", "urgency": None}
        for cluster in ("ai-chips", "competitor-pricing", "vc-funding"):
            assert engine._matches_trigger(trigger, _make_record(topic_cluster=cluster)) is True

    def test_prefix_wildcard_matches_matching_clusters(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.0, "topic_cluster_pattern": "ai-*", "urgency": None}
        assert engine._matches_trigger(trigger, _make_record(topic_cluster="ai-chips")) is True
        assert engine._matches_trigger(trigger, _make_record(topic_cluster="ai-investment")) is True

    def test_prefix_wildcard_rejects_non_matching_cluster(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.0, "topic_cluster_pattern": "ai-*", "urgency": None}
        assert engine._matches_trigger(trigger, _make_record(topic_cluster="competitor-pricing")) is False

    def test_exact_cluster_pattern_matches(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.0, "topic_cluster_pattern": "ai-chips", "urgency": None}
        assert engine._matches_trigger(trigger, _make_record(topic_cluster="ai-chips")) is True
        assert engine._matches_trigger(trigger, _make_record(topic_cluster="ai-investment")) is False

    def test_urgency_list_matches_when_record_in_list(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.0, "topic_cluster_pattern": "*", "urgency": ["high", "medium"]}
        assert engine._matches_trigger(trigger, _make_record(urgency="high")) is True
        assert engine._matches_trigger(trigger, _make_record(urgency="medium")) is True

    def test_urgency_list_rejects_when_record_not_in_list(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.0, "topic_cluster_pattern": "*", "urgency": ["high"]}
        assert engine._matches_trigger(trigger, _make_record(urgency="low")) is False

    def test_null_urgency_matches_all_records(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.0, "topic_cluster_pattern": "*", "urgency": None}
        for urgency in ("high", "medium", "low", ""):
            assert engine._matches_trigger(trigger, _make_record(urgency=urgency)) is True

    def test_urgency_string_matches_exact(self):
        engine = self._engine()
        trigger = {"min_mpi": 0.0, "topic_cluster_pattern": "*", "urgency": "high"}
        assert engine._matches_trigger(trigger, _make_record(urgency="high")) is True
        assert engine._matches_trigger(trigger, _make_record(urgency="low")) is False


# ── _derive_status ────────────────────────────────────────────────────────────


class TestDeriveStatus:
    def _ok(self, action_type="content_brief") -> ActionResult:
        return ActionResult(action_type=action_type, success=True, dry_run=False, detail="ok")

    def _fail(self, action_type="content_brief") -> ActionResult:
        return ActionResult(action_type=action_type, success=False, dry_run=False, detail="fail")

    def test_all_success(self):
        assert _derive_status([self._ok(), self._ok()]) == "success"

    def test_all_fail(self):
        assert _derive_status([self._fail(), self._fail()]) == "error"

    def test_partial(self):
        assert _derive_status([self._ok(), self._fail()]) == "partial"

    def test_empty_actions(self):
        assert _derive_status([]) == "skipped"


# ── Dry-run mode ──────────────────────────────────────────────────────────────


class TestDryRun:
    def test_dry_run_calls_action_execute_with_dry_run_true(self):
        engine = _make_engine()
        record = _make_record()

        fake_result = {"type": "content_brief", "success": True, "dry_run": True, "detail": "DRY RUN"}
        fake_slack = {"type": "slack_escalation", "success": True, "dry_run": True, "detail": "DRY RUN"}

        with patch("psycopg2.connect", return_value=_mock_conn_no_cooldown()):
            with patch("playbooks.actions.content_brief.execute", return_value=fake_result) as mock_exec:
                with patch("playbooks.actions.slack_escalation.execute", return_value=fake_slack):
                    engine.run(record, dry_run=True)

        mock_exec.assert_called_once()
        # dry_run is passed as a keyword argument
        assert mock_exec.call_args.kwargs.get("dry_run") is True

    def test_dry_run_action_results_have_dry_run_true(self):
        engine = _make_engine()
        record = _make_record()

        fake_ok = lambda cfg, rec, dry_run=False: {
            "type": cfg.get("type", ""), "success": True, "dry_run": dry_run, "detail": "ok"
        }

        with patch("psycopg2.connect", return_value=MagicMock()):
            with patch("playbooks.actions.content_brief.execute", side_effect=fake_ok):
                with patch("playbooks.actions.slack_escalation.execute", side_effect=fake_ok):
                    results = engine.run(record, dry_run=True)

        triggered = [r for r in results if r.triggered]
        assert len(triggered) >= 1
        for r in triggered:
            for action in r.actions:
                assert action.dry_run is True


# ── Cooldown enforcement ──────────────────────────────────────────────────────


class TestCooldown:
    def _cursor_with_row(self, row):
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = row
        return cur

    def test_not_in_cooldown_when_no_recent_runs(self):
        engine = _make_engine()
        conn = MagicMock()
        conn.cursor.return_value = self._cursor_with_row(None)
        assert engine._is_in_cooldown(conn, "high-confidence", "ai-chips", 60) is False

    def test_in_cooldown_when_recent_successful_run_exists(self):
        engine = _make_engine()
        conn = MagicMock()
        conn.cursor.return_value = self._cursor_with_row(("run-id-123",))
        assert engine._is_in_cooldown(conn, "high-confidence", "ai-chips", 60) is True

    def test_cooldown_check_db_error_assumes_not_in_cooldown(self):
        engine = _make_engine()
        conn = MagicMock()
        conn.cursor.side_effect = Exception("DB gone")
        # Should not raise, should assume not in cooldown
        assert engine._is_in_cooldown(conn, "pb", "cluster", 60) is False

    def test_cooldown_skipped_run_has_correct_flag(self):
        engine = _make_engine()
        record = _make_record()
        cur = self._cursor_with_row(("run-id-xyz",))
        conn = MagicMock()
        conn.cursor.return_value = cur

        fake_ok = {"type": "content_brief", "success": True, "dry_run": False, "detail": "ok"}

        with patch("psycopg2.connect", return_value=conn):
            with patch("playbooks.actions.content_brief.execute", return_value=fake_ok):
                with patch("playbooks.actions.slack_escalation.execute", return_value=fake_ok):
                    results = engine.run(record, dry_run=False)

        triggered_cooled = [r for r in results if r.triggered and r.cooldown_skipped]
        assert len(triggered_cooled) >= 1
        for r in triggered_cooled:
            assert r.status == "skipped"
            assert r.actions == []


# ── Partial failure handling ──────────────────────────────────────────────────


class TestPartialFailure:
    def test_action_failure_does_not_block_subsequent_action(self):
        playbook = dict(
            _DEFAULT_PLAYBOOKS[0],
            actions=[{"type": "bid_adjustment"}, {"type": "content_brief"}],
        )
        engine = _make_engine([playbook])
        record = _make_record()

        fail_result = {"type": "bid_adjustment", "success": False, "dry_run": False,
                       "detail": "GOOGLE_ADS_CAMPAIGN_IDS not set", "error": "missing env var"}
        ok_result = {"type": "content_brief", "success": True, "dry_run": False, "detail": "sent"}

        with patch("psycopg2.connect", return_value=_mock_conn_no_cooldown()):
            with patch("playbooks.actions.bid_adjustment.execute", return_value=fail_result):
                with patch("playbooks.actions.content_brief.execute", return_value=ok_result) as mock_brief:
                    results = engine.run(record)

        mock_brief.assert_called_once()
        triggered = [r for r in results if r.triggered]
        assert len(triggered) == 1
        assert triggered[0].status == "partial"

    def test_all_actions_fail_gives_error_status(self):
        engine = _make_engine()
        record = _make_record()
        fail = {"type": "x", "success": False, "dry_run": False, "detail": "fail"}

        with patch("psycopg2.connect", return_value=_mock_conn_no_cooldown()):
            with patch("playbooks.actions.content_brief.execute", return_value=fail):
                with patch("playbooks.actions.slack_escalation.execute", return_value=fail):
                    results = engine.run(record)

        triggered = [r for r in results if r.triggered]
        assert triggered[0].status == "error"

    def test_unknown_action_type_does_not_raise(self):
        playbook = dict(_DEFAULT_PLAYBOOKS[0], actions=[{"type": "unknown_action_xyz"}])
        engine = _make_engine([playbook])
        record = _make_record()

        with patch("psycopg2.connect", return_value=_mock_conn_no_cooldown()):
            results = engine.run(record)

        triggered = [r for r in results if r.triggered]
        assert len(triggered) == 1
        assert triggered[0].status == "error"
        assert triggered[0].actions[0].error == "not in registry"

    def test_action_module_raises_does_not_propagate(self):
        engine = _make_engine()
        record = _make_record()

        with patch("psycopg2.connect", return_value=_mock_conn_no_cooldown()):
            with patch("playbooks.actions.content_brief.execute", side_effect=RuntimeError("crash")):
                with patch("playbooks.actions.slack_escalation.execute", return_value={
                    "type": "slack_escalation", "success": True, "dry_run": False, "detail": "ok"
                }):
                    results = engine.run(record)

        triggered = [r for r in results if r.triggered]
        assert triggered[0].status == "partial"
        fail_action = triggered[0].actions[0]
        assert fail_action.success is False
        assert "crash" in (fail_action.error or "")


# ── DB connection failure ─────────────────────────────────────────────────────


class TestEngineRun:
    def test_db_connection_failure_returns_empty_list(self):
        engine = _make_engine()
        record = _make_record()

        with patch("psycopg2.connect", side_effect=psycopg2.OperationalError("DB down")):
            results = engine.run(record)

        assert results == []

    def test_non_triggered_playbook_returns_result_with_triggered_false(self):
        engine = _make_engine()
        record = _make_record(mpi_score=0.5)  # below min_mpi=0.85

        with patch("psycopg2.connect", return_value=MagicMock()):
            results = engine.run(record)

        assert len(results) == 1
        assert results[0].triggered is False
        assert results[0].status == "skipped"

    def test_no_playbooks_returns_empty_list(self):
        engine = _make_engine([])
        with patch("psycopg2.connect", return_value=MagicMock()):
            results = engine.run(_make_record())
        assert results == []
