"""Unit tests for predictive.mpi_archiver.

All DB I/O is mocked. Tests verify:
  - archive_results: idempotency, correct upsert SQL, empty-input guard
  - get_baseline: 7-day average path, < 12-row fallback, DB error fallback
  - query_history: SQL parameter mapping, empty result handling
  - _to_5min_bucket: boundary alignment
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch, PropertyMock

import pytest

from predictive.mpi_archiver import (
    _FALLBACK_BASELINE,
    _MIN_ROWS_FOR_BASELINE,
    _to_5min_bucket,
    archive_results,
    get_baseline,
    query_history,
)


# ── _to_5min_bucket ───────────────────────────────────────────────────────────


class TestTo5MinBucket:
    def test_already_aligned(self):
        dt = datetime(2026, 4, 29, 14, 10, 0, tzinfo=timezone.utc)
        assert _to_5min_bucket(dt) == dt.replace(second=0, microsecond=0)

    def test_rounds_down(self):
        dt = datetime(2026, 4, 29, 14, 13, 47, 999999, tzinfo=timezone.utc)
        expected = datetime(2026, 4, 29, 14, 10, 0, tzinfo=timezone.utc)
        assert _to_5min_bucket(dt) == expected

    def test_minute_zero(self):
        dt = datetime(2026, 4, 29, 9, 0, 59, tzinfo=timezone.utc)
        expected = datetime(2026, 4, 29, 9, 0, 0, tzinfo=timezone.utc)
        assert _to_5min_bucket(dt) == expected

    def test_minute_59(self):
        dt = datetime(2026, 4, 29, 23, 59, 30, tzinfo=timezone.utc)
        expected = datetime(2026, 4, 29, 23, 55, 0, tzinfo=timezone.utc)
        assert _to_5min_bucket(dt) == expected

    def test_strips_microseconds(self):
        dt = datetime(2026, 4, 29, 12, 7, 3, 500000, tzinfo=timezone.utc)
        bucket = _to_5min_bucket(dt)
        assert bucket.second == 0
        assert bucket.microsecond == 0
        assert bucket.minute == 5


# ── archive_results ───────────────────────────────────────────────────────────


def _make_result(**overrides) -> dict:
    base = dict(
        topic_cluster="ai-chips",
        mpi_score=0.85,
        signal_count=42,
        computed_at="2026-04-29T14:07:00+00:00",
        window_minutes=60,
    )
    base.update(overrides)
    return base


class TestArchiveResults:
    def test_returns_zero_for_empty_list(self):
        assert archive_results([]) == 0

    @patch("predictive.mpi_archiver.psycopg2.connect")
    def test_returns_count_of_rows_written(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        results = [_make_result(), _make_result(topic_cluster="ev-trucks")]
        count = archive_results(results, dsn="postgresql://test")

        assert count == 2

    @patch("predictive.mpi_archiver.psycopg2.connect")
    def test_upsert_sql_uses_on_conflict(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        archive_results([_make_result()], dsn="postgresql://test")

        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "ON CONFLICT" in executed_sql
        assert "DO UPDATE" in executed_sql

    @patch("predictive.mpi_archiver.psycopg2.connect")
    def test_commits_after_all_rows(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        archive_results([_make_result(), _make_result(topic_cluster="x")], dsn="postgresql://test")
        mock_conn.commit.assert_called_once()

    @patch("predictive.mpi_archiver.psycopg2.connect")
    def test_returns_zero_on_db_error(self, mock_connect):
        import psycopg2

        mock_connect.side_effect = psycopg2.OperationalError("connection refused")
        count = archive_results([_make_result()], dsn="postgresql://test")
        assert count == 0

    @patch("predictive.mpi_archiver.psycopg2.connect")
    def test_handles_iso_string_computed_at(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        result = _make_result(computed_at="2026-04-29T14:07:33+00:00")
        archive_results([result], dsn="postgresql://test")

        # The bucket passed should be 14:05:00 (floor of 14:07)
        call_args = mock_cursor.execute.call_args[0][1]
        bucket = call_args[1]  # second positional param
        assert bucket.minute == 5
        assert bucket.second == 0

    @patch("predictive.mpi_archiver.psycopg2.connect")
    def test_handles_missing_computed_at(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        result = _make_result()
        del result["computed_at"]
        count = archive_results([result], dsn="postgresql://test")
        assert count == 1


# ── get_baseline ──────────────────────────────────────────────────────────────


class TestGetBaseline:
    def _mock_conn(self, row_count: int, avg_signals: float) -> MagicMock:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = (row_count, avg_signals)
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return conn

    def test_returns_avg_when_enough_rows(self):
        conn = self._mock_conn(row_count=288, avg_signals=25.7)
        baseline = get_baseline(conn, "ai-chips", window_minutes=60)
        assert baseline == pytest.approx(25.7)

    def test_returns_fallback_when_row_count_below_min(self):
        conn = self._mock_conn(row_count=_MIN_ROWS_FOR_BASELINE - 1, avg_signals=50.0)
        baseline = get_baseline(conn, "ai-chips")
        assert baseline == pytest.approx(_FALLBACK_BASELINE)

    def test_returns_fallback_when_zero_rows(self):
        conn = self._mock_conn(row_count=0, avg_signals=0.0)
        baseline = get_baseline(conn, "new-cluster")
        assert baseline == pytest.approx(_FALLBACK_BASELINE)

    def test_clamps_avg_to_minimum_1(self):
        # avg_signals could theoretically round to 0 with very sparse data
        conn = self._mock_conn(row_count=100, avg_signals=0.3)
        baseline = get_baseline(conn, "sparse-cluster")
        assert baseline >= 1.0

    @patch("predictive.mpi_archiver.psycopg2.connect")
    def test_accepts_dsn_string(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (300, 18.5)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        baseline = get_baseline("postgresql://test", "ai-chips")

        mock_connect.assert_called_once_with("postgresql://test")
        assert baseline == pytest.approx(18.5)

    def test_returns_fallback_on_db_error(self):
        import psycopg2

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(
            side_effect=psycopg2.OperationalError("DB gone")
        )
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        baseline = get_baseline(conn, "ai-chips")
        assert baseline == pytest.approx(_FALLBACK_BASELINE)

    def test_boundary_exactly_at_min_rows(self):
        # Exactly _MIN_ROWS_FOR_BASELINE should return the real average
        conn = self._mock_conn(row_count=_MIN_ROWS_FOR_BASELINE, avg_signals=20.0)
        baseline = get_baseline(conn, "ai-chips")
        assert baseline == pytest.approx(20.0)


# ── query_history ─────────────────────────────────────────────────────────────


class TestQueryHistory:
    def _mock_conn_with_rows(self, rows: list[dict]) -> MagicMock:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return conn

    def test_returns_list_of_dicts(self):
        row = {
            "recorded_at": datetime(2026, 4, 29, 14, 0, tzinfo=timezone.utc),
            "topic_cluster": "ai-chips",
            "mpi_score": 0.85,
            "signal_count": 42,
            "window_minutes": 60,
        }
        conn = self._mock_conn_with_rows([row])
        result = query_history(conn)
        assert len(result) == 1
        assert result[0]["topic_cluster"] == "ai-chips"

    def test_returns_empty_list_on_no_rows(self):
        conn = self._mock_conn_with_rows([])
        assert query_history(conn) == []

    def test_returns_empty_list_on_db_error(self):
        import psycopg2

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(
            side_effect=psycopg2.OperationalError("gone")
        )
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = query_history(conn)
        assert result == []

    def test_passes_cluster_filter_as_param(self):
        conn = self._mock_conn_with_rows([])
        query_history(conn, cluster="ai-chips")
        cursor = conn.cursor.return_value.__enter__.return_value
        params = cursor.execute.call_args[0][1]
        # cluster param appears twice (for IS NULL check and equality)
        assert params[0] == "ai-chips"
        assert params[1] == "ai-chips"

    def test_passes_none_when_no_cluster_filter(self):
        conn = self._mock_conn_with_rows([])
        query_history(conn, cluster=None)
        cursor = conn.cursor.return_value.__enter__.return_value
        params = cursor.execute.call_args[0][1]
        assert params[0] is None
        assert params[1] is None


# ── Response shape (integration-level) ───────────────────────────────────────


class TestResponseShape:
    """Verify the dict keys returned by query_history match what the API router expects."""

    def test_row_has_all_required_keys(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = [{
            "recorded_at": datetime(2026, 4, 29, 14, 0, tzinfo=timezone.utc),
            "topic_cluster": "ev-trucks",
            "mpi_score": 0.77,
            "signal_count": 18,
            "window_minutes": 60,
        }]
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        rows = query_history(conn)
        row = rows[0]
        for key in ("recorded_at", "topic_cluster", "mpi_score", "signal_count", "window_minutes"):
            assert key in row, f"Missing key: {key}"
