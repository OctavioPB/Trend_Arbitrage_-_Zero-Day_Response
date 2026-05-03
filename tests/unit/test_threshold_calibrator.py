"""Unit tests for predictive.threshold_calibrator.

All DB interactions are mocked. Tests never hit the network or database.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from predictive.threshold_calibrator import (
    ThresholdCalibrator,
    _HIGH_PRECISION_CUTOFF,
    _LOW_PRECISION_CUTOFF,
    _POSITIVE_CTR_THRESHOLD,
    _THRESHOLD_MAX,
    _THRESHOLD_MIN,
    _THRESHOLD_STEP_DOWN,
    _THRESHOLD_STEP_UP,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_calibrator() -> ThresholdCalibrator:
    return ThresholdCalibrator()


def _mock_conn(measured_rows: list[dict], total_issued: int = 50) -> MagicMock:
    """Return a mock psycopg2 connection backed by canned query results."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    # _load_measured_outcomes returns (golden_record_id, ctr) rows
    measured_db_rows = [(r["golden_record_id"], r["ctr"]) for r in measured_rows]
    cur.description = [("golden_record_id",), ("ctr",)]

    # _count_total_issued returns a scalar
    cur.fetchall.return_value = measured_db_rows
    cur.fetchone.return_value = (total_issued,)

    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def _hit_rows(n: int, start: int = 0) -> list[dict]:
    """Generate n 'hit' rows (CTR above threshold)."""
    return [
        {"golden_record_id": f"gr-{start + i:03d}", "ctr": _POSITIVE_CTR_THRESHOLD + 0.01}
        for i in range(n)
    ]


def _miss_rows(n: int, start: int = 0) -> list[dict]:
    """Generate n 'miss' rows (CTR below threshold)."""
    return [
        {"golden_record_id": f"gr-miss-{start + i:03d}", "ctr": _POSITIVE_CTR_THRESHOLD - 0.01}
        for i in range(n)
    ]


# ── Sample threshold ──────────────────────────────────────────────────────────


class TestMinSamples:
    def test_returns_none_when_zero_samples(self):
        cal = _make_calibrator()
        conn = _mock_conn([], total_issued=0)
        with patch.object(cal, "_load_current_weights", return_value={"reddit": 1.0}):
            with patch.object(cal, "_load_source_counts", return_value={}):
                result = cal.compute(conn, window_days=30, min_samples=30)
        assert result is None

    def test_returns_none_when_below_min_samples(self):
        cal = _make_calibrator()
        rows = _hit_rows(29)
        conn = _mock_conn(rows)

        def fake_outcomes(c, w):
            return rows

        def fake_total(c, w):
            return 100

        with patch.object(cal, "_load_measured_outcomes", side_effect=fake_outcomes):
            with patch.object(cal, "_count_total_issued", side_effect=fake_total):
                result = cal.compute(conn, window_days=30, min_samples=30)
        assert result is None

    def test_returns_result_at_exactly_min_samples(self):
        cal = _make_calibrator()
        rows = _hit_rows(30)

        with patch.object(cal, "_load_measured_outcomes", return_value=rows):
            with patch.object(cal, "_count_total_issued", return_value=100):
                with patch.object(cal, "_load_current_weights", return_value={"reddit": 1.0}):
                    with patch.object(cal, "_load_source_counts", return_value={}):
                        result = cal.compute(conn=MagicMock(), window_days=30, min_samples=30)
        assert result is not None
        assert result.sample_count == 30


# ── Precision computation ─────────────────────────────────────────────────────


class TestPrecision:
    def _run(self, hits: int, misses: int) -> float:
        cal = _make_calibrator()
        rows = _hit_rows(hits) + _miss_rows(misses)
        with patch.object(cal, "_load_measured_outcomes", return_value=rows):
            with patch.object(cal, "_count_total_issued", return_value=100):
                with patch.object(cal, "_load_current_weights", return_value={"reddit": 1.0}):
                    with patch.object(cal, "_load_source_counts", return_value={}):
                        result = cal.compute(conn=MagicMock(), window_days=30, min_samples=1)
        assert result is not None
        return result.precision

    def test_all_hits(self):
        assert self._run(hits=30, misses=0) == pytest.approx(1.0)

    def test_all_misses(self):
        assert self._run(hits=0, misses=30) == pytest.approx(0.0)

    def test_half_half(self):
        assert self._run(hits=15, misses=15) == pytest.approx(0.5)

    def test_precision_rounded_to_4dp(self):
        p = self._run(hits=10, misses=20)
        assert p == round(10 / 30, 4)


# ── Recall computation ────────────────────────────────────────────────────────


class TestRecall:
    def test_recall_proxy_hits_over_total_issued(self):
        cal = _make_calibrator()
        rows = _hit_rows(20)
        with patch.object(cal, "_load_measured_outcomes", return_value=rows):
            with patch.object(cal, "_count_total_issued", return_value=100):
                with patch.object(cal, "_load_current_weights", return_value={"reddit": 1.0}):
                    with patch.object(cal, "_load_source_counts", return_value={}):
                        result = cal.compute(conn=MagicMock(), window_days=30, min_samples=1)
        # 20 hits / 100 total issued = 0.2
        assert result.recall == pytest.approx(0.2)


# ── Threshold suggestion ──────────────────────────────────────────────────────


class TestThresholdSuggestion:
    def _suggest(self, current: float, precision: float) -> float:
        cal = _make_calibrator()
        return cal._suggest_threshold(current, precision)

    def test_high_precision_lowers_threshold(self):
        # precision >= _HIGH_PRECISION_CUTOFF → decrease by STEP_DOWN
        result = self._suggest(current=0.72, precision=_HIGH_PRECISION_CUTOFF)
        assert result == pytest.approx(0.72 - _THRESHOLD_STEP_DOWN)

    def test_low_precision_raises_threshold(self):
        # precision < _LOW_PRECISION_CUTOFF → increase by STEP_UP
        result = self._suggest(current=0.72, precision=_LOW_PRECISION_CUTOFF - 0.01)
        assert result == pytest.approx(0.72 + _THRESHOLD_STEP_UP)

    def test_mid_precision_no_change(self):
        # precision between LOW and HIGH → no change
        mid = (_LOW_PRECISION_CUTOFF + _HIGH_PRECISION_CUTOFF) / 2
        result = self._suggest(current=0.72, precision=mid)
        assert result == pytest.approx(0.72)

    def test_floor_enforced(self):
        # Would go below min — clamp to _THRESHOLD_MIN
        result = self._suggest(current=_THRESHOLD_MIN + 0.01, precision=1.0)
        assert result == pytest.approx(_THRESHOLD_MIN)

    def test_ceiling_enforced(self):
        # Would exceed max — clamp to _THRESHOLD_MAX
        result = self._suggest(current=_THRESHOLD_MAX - 0.01, precision=0.0)
        assert result == pytest.approx(_THRESHOLD_MAX)

    def test_already_at_floor_stays_at_floor(self):
        result = self._suggest(current=_THRESHOLD_MIN, precision=1.0)
        assert result == pytest.approx(_THRESHOLD_MIN)

    def test_already_at_ceiling_stays_at_ceiling(self):
        result = self._suggest(current=_THRESHOLD_MAX, precision=0.0)
        assert result == pytest.approx(_THRESHOLD_MAX)

    def test_result_has_3dp(self):
        result = self._suggest(current=0.721, precision=1.0)
        # 0.721 - 0.02 = 0.701, rounded to 3dp
        assert result == pytest.approx(0.701)


# ── Source weight suggestion ──────────────────────────────────────────────────


class TestSourceWeights:
    def _run_weights(
        self,
        source_counts: dict[tuple[str, str], float],
        current_weights: dict[str, float] | None = None,
        hit_ids: set[str] | None = None,
        miss_ids: set[str] | None = None,
    ) -> dict[str, float]:
        cal = _make_calibrator()
        if current_weights is None:
            current_weights = {"reddit": 1.0, "twitter": 0.9, "news": 1.2}
        if hit_ids is None:
            hit_ids = {"gr-001"}
        if miss_ids is None:
            miss_ids = {"gr-002"}

        with patch.object(cal, "_load_source_counts", return_value=source_counts):
            return cal._suggest_weights(
                conn=MagicMock(),
                window_days=30,
                hit_ids=hit_ids,
                miss_ids=miss_ids,
                current_weights=current_weights,
            )

    def test_returns_current_weights_when_no_source_data(self):
        current = {"reddit": 1.0, "twitter": 0.9}
        result = self._run_weights({}, current_weights=current)
        assert result == current

    def test_high_hit_source_weight_increases(self):
        # reddit appears heavily in hit records, twitter in miss records
        source_counts = {
            ("gr-001", "reddit"): 80.0,  # hit record
            ("gr-001", "twitter"): 20.0,
            ("gr-002", "reddit"): 10.0,  # miss record
            ("gr-002", "twitter"): 90.0,
        }
        result = self._run_weights(source_counts)
        # reddit's contribution to hits (80/100) > its overall share (90/200)
        assert result["reddit"] > 1.0  # default weight was 1.0

    def test_weights_mean_preserved(self):
        source_counts = {
            ("gr-001", "reddit"): 80.0,
            ("gr-001", "twitter"): 20.0,
            ("gr-002", "reddit"): 20.0,
            ("gr-002", "twitter"): 80.0,
        }
        current = {"reddit": 1.0, "twitter": 1.0}
        result = self._run_weights(
            source_counts,
            current_weights=current,
            hit_ids={"gr-001"},
            miss_ids={"gr-002"},
        )
        # Mean of proposed weights ≈ mean of current weights (1.0)
        mean_proposed = sum(result.values()) / len(result)
        mean_current = sum(current.values()) / len(current)
        assert mean_proposed == pytest.approx(mean_current, rel=0.01)

    def test_all_weights_positive(self):
        # Even a source with zero hit contribution keeps a positive weight (floor)
        source_counts = {
            ("gr-001", "reddit"): 100.0,  # only in hit
            ("gr-002", "twitter"): 100.0,  # only in miss
        }
        current = {"reddit": 1.0, "twitter": 1.0}
        result = self._run_weights(
            source_counts,
            current_weights=current,
            hit_ids={"gr-001"},
            miss_ids={"gr-002"},
        )
        assert all(v > 0 for v in result.values())


# ── write_proposal ────────────────────────────────────────────────────────────


class TestWriteProposal:
    def test_writes_correct_fields_and_returns_id(self):
        from predictive.threshold_calibrator import CalibrationResult

        cal = _make_calibrator()
        result = CalibrationResult(
            precision=0.75,
            recall=0.40,
            sample_count=35,
            current_mpi_threshold=0.72,
            proposed_mpi_threshold=0.70,
            current_source_weights={"reddit": 1.0},
            proposed_source_weights={"reddit": 1.1},
        )

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = ("proposal-uuid-123",)

        conn = MagicMock()
        conn.cursor.return_value = cur

        proposal_id = cal.write_proposal(conn, result)
        assert proposal_id == "proposal-uuid-123"
        cur.execute.assert_called_once()

        # Verify the execute call includes the right values
        call_args = cur.execute.call_args[0]
        params = call_args[1]
        assert params[0] == pytest.approx(0.70)   # proposed_mpi_threshold
        assert params[2] == pytest.approx(0.75)   # precision
        assert params[3] == pytest.approx(0.40)   # recall
        assert params[4] == 35                     # sample_count

    def test_proposed_weights_serialised_as_json(self):
        from predictive.threshold_calibrator import CalibrationResult

        cal = _make_calibrator()
        result = CalibrationResult(
            precision=0.8,
            recall=0.5,
            sample_count=40,
            current_mpi_threshold=0.72,
            proposed_mpi_threshold=0.70,
            current_source_weights={"reddit": 1.0},
            proposed_source_weights={"reddit": 1.2, "twitter": 0.8},
        )

        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = ("some-uuid",)

        conn = MagicMock()
        conn.cursor.return_value = cur

        cal.write_proposal(conn, result)
        params = cur.execute.call_args[0][1]
        weights_json = json.loads(params[1])
        assert weights_json["reddit"] == pytest.approx(1.2)
        assert weights_json["twitter"] == pytest.approx(0.8)


# ── load_current_weights ──────────────────────────────────────────────────────


class TestLoadWeights:
    def test_loads_from_json_file(self, tmp_path: Path):
        weights_file = tmp_path / "source_weights.json"
        weights_file.write_text(
            json.dumps({"_comment": "ignore", "reddit": 1.3, "news": 0.8}),
            encoding="utf-8",
        )
        cal = _make_calibrator()

        import predictive.threshold_calibrator as mod

        original = mod._WEIGHTS_PATH
        mod._WEIGHTS_PATH = weights_file
        try:
            result = cal._load_current_weights()
        finally:
            mod._WEIGHTS_PATH = original

        assert "_comment" not in result
        assert result["reddit"] == pytest.approx(1.3)
        assert result["news"] == pytest.approx(0.8)

    def test_returns_defaults_when_file_missing(self):
        cal = _make_calibrator()

        import predictive.threshold_calibrator as mod

        original = mod._WEIGHTS_PATH
        mod._WEIGHTS_PATH = Path("/nonexistent/weights.json")
        try:
            result = cal._load_current_weights()
        finally:
            mod._WEIGHTS_PATH = original

        assert "reddit" in result
        assert all(v > 0 for v in result.values())
