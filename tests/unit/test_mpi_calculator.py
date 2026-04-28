"""Unit tests for the MPI calculator.

No DB connections — all tests pass fixed signals and weights directly.
The `now` parameter is always set explicitly to avoid time-dependent behavior.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from predictive.mpi_calculator import (
    MPIResult,
    _compute_sentiment,
    _compute_velocity,
    _compute_volume,
    calculate_mpi,
    load_weights,
)

_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)
_WEIGHTS = {"volume": 0.4, "velocity": 0.35, "sentiment": 0.25}


# ── helpers ───────────────────────────────────────────────────────────────────


def _signal(
    minutes_ago: float = 5.0,
    sentiment: str = "positive",
    topic_tags: list[str] | None = None,
) -> dict:
    return {
        "collected_at": _NOW - timedelta(minutes=minutes_ago),
        "sentiment": sentiment,
        "topic_tags": topic_tags or ["ai"],
    }


def _signals(
    n: int,
    minutes_ago: float = 5.0,
    sentiment: str = "positive",
) -> list[dict]:
    return [_signal(minutes_ago, sentiment) for _ in range(n)]


# ── load_weights ──────────────────────────────────────────────────────────────


class TestLoadWeights:
    def test_loads_from_json(self, tmp_path: Path) -> None:
        weights_file = tmp_path / "weights.json"
        weights_file.write_text(json.dumps({"volume": 0.5, "velocity": 0.3, "sentiment": 0.2}))
        with patch("predictive.mpi_calculator._WEIGHTS_PATH", weights_file):
            result = load_weights()
        assert result["volume"] == pytest.approx(0.5)

    def test_strips_comment_keys(self, tmp_path: Path) -> None:
        weights_file = tmp_path / "weights.json"
        weights_file.write_text(json.dumps({"volume": 0.4, "_comment": "ignored", "velocity": 0.35, "sentiment": 0.25}))
        with patch("predictive.mpi_calculator._WEIGHTS_PATH", weights_file):
            result = load_weights()
        assert "_comment" not in result

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        with patch("predictive.mpi_calculator._WEIGHTS_PATH", tmp_path / "nonexistent.json"):
            result = load_weights()
        assert set(result.keys()) == {"volume", "velocity", "sentiment"}

    def test_invalid_json_returns_defaults(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json}")
        with patch("predictive.mpi_calculator._WEIGHTS_PATH", bad_file):
            result = load_weights()
        assert result["volume"] == pytest.approx(0.4)


# ── _compute_volume ───────────────────────────────────────────────────────────


class TestComputeVolume:
    def test_normal_case(self) -> None:
        # 10 signals with baseline 10 → volume = 1.0
        assert _compute_volume(10, 10.0) == pytest.approx(1.0)

    def test_below_baseline(self) -> None:
        # 5 signals with baseline 10 → volume = 0.5
        assert _compute_volume(5, 10.0) == pytest.approx(0.5)

    def test_clamped_at_one(self) -> None:
        # 20 signals with baseline 10 → would be 2.0 but clamped to 1.0
        assert _compute_volume(20, 10.0) == pytest.approx(1.0)

    def test_zero_signals(self) -> None:
        assert _compute_volume(0, 10.0) == pytest.approx(0.0)

    def test_zero_baseline_with_signals(self) -> None:
        # No baseline data but signals present → treat as significant
        assert _compute_volume(5, 0.0) == pytest.approx(1.0)

    def test_zero_baseline_no_signals(self) -> None:
        assert _compute_volume(0, 0.0) == pytest.approx(0.0)


# ── _compute_velocity ─────────────────────────────────────────────────────────


class TestComputeVelocity:
    def test_empty_signals(self) -> None:
        assert _compute_velocity([], _NOW) == pytest.approx(0.0)

    def test_new_trend_no_prior_window(self) -> None:
        # All signals in last 15 min, none in prev 15 min → velocity = 1.0
        recent = [_signal(5) for _ in range(5)]
        assert _compute_velocity(recent, _NOW) == pytest.approx(1.0)

    def test_velocity_cliff_no_activity_at_all(self) -> None:
        # Signals exist but all older than 30 min → last_15=0, prev_15=0 → 0.0
        old = [_signal(45) for _ in range(5)]
        assert _compute_velocity(old, _NOW) == pytest.approx(0.0)

    def test_doubled_growth(self) -> None:
        # prev_15: 5 signals, last_15: 10 signals → raw = (10/5) - 1 = 1.0
        prev = [_signal(20) for _ in range(5)]
        last = [_signal(5) for _ in range(10)]
        assert _compute_velocity(prev + last, _NOW) == pytest.approx(1.0)

    def test_flat_trend(self) -> None:
        # prev_15: 5, last_15: 5 → raw = 0.0
        prev = [_signal(20) for _ in range(5)]
        last = [_signal(5) for _ in range(5)]
        assert _compute_velocity(prev + last, _NOW) == pytest.approx(0.0)

    def test_declining_trend_clamped_to_zero(self) -> None:
        # prev_15: 10, last_15: 2 → raw = -0.8, clamped to 0.0
        prev = [_signal(20) for _ in range(10)]
        last = [_signal(5) for _ in range(2)]
        assert _compute_velocity(prev + last, _NOW) == pytest.approx(0.0)

    def test_partial_growth_between_zero_and_one(self) -> None:
        # prev_15: 4, last_15: 6 → raw = 0.5
        prev = [_signal(20) for _ in range(4)]
        last = [_signal(5) for _ in range(6)]
        result = _compute_velocity(prev + last, _NOW)
        assert 0.0 < result < 1.0
        assert result == pytest.approx(0.5)


# ── _compute_sentiment ────────────────────────────────────────────────────────


class TestComputeSentiment:
    def test_all_positive(self) -> None:
        signals = [_signal(sentiment="positive") for _ in range(5)]
        assert _compute_sentiment(signals) == pytest.approx(1.0)

    def test_all_negative(self) -> None:
        signals = [_signal(sentiment="negative") for _ in range(5)]
        assert _compute_sentiment(signals) == pytest.approx(0.0)

    def test_all_neutral(self) -> None:
        signals = [_signal(sentiment="neutral") for _ in range(5)]
        assert _compute_sentiment(signals) == pytest.approx(0.0)

    def test_mixed(self) -> None:
        signals = (
            [_signal(sentiment="positive")] * 3
            + [_signal(sentiment="negative")] * 2
        )
        assert _compute_sentiment(signals) == pytest.approx(0.6)

    def test_empty_signals(self) -> None:
        assert _compute_sentiment([]) == pytest.approx(0.0)


# ── calculate_mpi (full function) ────────────────────────────────────────────


class TestCalculateMPI:
    def test_returns_mpi_result(self) -> None:
        result = calculate_mpi(
            signals=_signals(5),
            baseline_avg_signals=5.0,
            now=_NOW,
            weights=_WEIGHTS,
        )
        assert isinstance(result, MPIResult)

    def test_mpi_score_always_between_zero_and_one(self) -> None:
        """Property: MPI in [0, 1] regardless of input."""
        cases = [
            _signals(0),
            _signals(100),
            _signals(5, sentiment="negative"),
            [_signal(5, "positive")] * 50 + [_signal(20, "negative")] * 3,
        ]
        for sigs in cases:
            result = calculate_mpi(sigs, baseline_avg_signals=10.0, now=_NOW, weights=_WEIGHTS)
            assert 0.0 <= result.mpi_score <= 1.0, f"MPI out of range for {len(sigs)} signals"

    def test_zero_signals_gives_zero_mpi(self) -> None:
        result = calculate_mpi([], baseline_avg_signals=10.0, now=_NOW, weights=_WEIGHTS)
        assert result.mpi_score == pytest.approx(0.0)

    def test_all_negative_sentiment_reduces_mpi(self) -> None:
        all_positive = calculate_mpi(
            _signals(5, sentiment="positive"),
            baseline_avg_signals=5.0,
            now=_NOW,
            weights=_WEIGHTS,
        )
        all_negative = calculate_mpi(
            _signals(5, sentiment="negative"),
            baseline_avg_signals=5.0,
            now=_NOW,
            weights=_WEIGHTS,
        )
        assert all_negative.mpi_score < all_positive.mpi_score

    def test_changing_weights_changes_mpi(self) -> None:
        # Mixed signals: some positive, some neutral, partial volume, no velocity
        # (all signals older than 30 min so velocity = 0.0, not all positive so
        #  sentiment < 1.0, baseline 20 but only 5 signals so volume < 1.0)
        sigs = (
            [_signal(40, "positive")] * 3
            + [_signal(45, "neutral")] * 2
        )
        w1 = {"volume": 0.8, "velocity": 0.1, "sentiment": 0.1}
        w2 = {"volume": 0.1, "velocity": 0.1, "sentiment": 0.8}
        r1 = calculate_mpi(sigs, baseline_avg_signals=20.0, now=_NOW, weights=w1)
        r2 = calculate_mpi(sigs, baseline_avg_signals=20.0, now=_NOW, weights=w2)
        # Different weights applied to different component values → different MPI
        assert r1.mpi_score != r2.mpi_score

    def test_result_contains_all_component_scores(self) -> None:
        result = calculate_mpi(_signals(5), baseline_avg_signals=5.0, now=_NOW, weights=_WEIGHTS)
        assert 0.0 <= result.volume_score <= 1.0
        assert 0.0 <= result.velocity_score <= 1.0
        assert 0.0 <= result.sentiment_score <= 1.0

    def test_result_contains_signal_count(self) -> None:
        result = calculate_mpi(_signals(7), baseline_avg_signals=5.0, now=_NOW, weights=_WEIGHTS)
        assert result.signal_count == 7

    def test_topic_cluster_propagated(self) -> None:
        result = calculate_mpi(
            _signals(3),
            topic_cluster="ev-charging",
            baseline_avg_signals=5.0,
            now=_NOW,
            weights=_WEIGHTS,
        )
        assert result.topic_cluster == "ev-charging"

    def test_velocity_cliff_new_trend(self) -> None:
        # All signals in the last 15 min → new trend → velocity = 1.0
        sigs = [_signal(5, "positive") for _ in range(5)]
        result = calculate_mpi(sigs, baseline_avg_signals=5.0, now=_NOW, weights=_WEIGHTS)
        assert result.velocity_score == pytest.approx(1.0)

    def test_iso_string_collected_at_accepted(self) -> None:
        sigs = [
            {
                "collected_at": (_NOW - timedelta(minutes=5)).isoformat(),
                "sentiment": "positive",
            }
        ]
        result = calculate_mpi(sigs, baseline_avg_signals=1.0, now=_NOW, weights=_WEIGHTS)
        assert result.signal_count == 1

    def test_signals_outside_window_excluded(self) -> None:
        in_window = _signals(3, minutes_ago=30)
        out_of_window = _signals(10, minutes_ago=90)  # 90 min ago, outside 60 min window
        result = calculate_mpi(
            in_window + out_of_window,
            baseline_avg_signals=5.0,
            window_minutes=60,
            now=_NOW,
            weights=_WEIGHTS,
        )
        assert result.signal_count == 3

    def test_mpi_score_rounded_to_three_decimals(self) -> None:
        result = calculate_mpi(_signals(3), baseline_avg_signals=5.0, now=_NOW, weights=_WEIGHTS)
        assert result.mpi_score == round(result.mpi_score, 3)

    def test_weights_stored_in_result(self) -> None:
        result = calculate_mpi(_signals(3), baseline_avg_signals=5.0, now=_NOW, weights=_WEIGHTS)
        assert result.weights == _WEIGHTS


# ── golden_record expires_at ─────────────────────────────────────────────────


class TestComputeExpiresAt:
    def test_high_velocity_shorter_ttl(self) -> None:
        from predictive.golden_record_generator import _compute_expires_at

        low_vel = _compute_expires_at(0.0, _NOW)
        high_vel = _compute_expires_at(1.0, _NOW)
        assert high_vel < low_vel

    def test_ttl_not_fixed_offset(self) -> None:
        from predictive.golden_record_generator import _compute_expires_at

        e1 = _compute_expires_at(0.2, _NOW)
        e2 = _compute_expires_at(0.8, _NOW)
        assert e1 != e2

    def test_ttl_minimum_enforced(self) -> None:
        from predictive.golden_record_generator import _MIN_TTL_HOURS, _compute_expires_at

        expires = _compute_expires_at(1.0, _NOW)
        actual_hours = (expires - _NOW).total_seconds() / 3600
        assert actual_hours >= _MIN_TTL_HOURS - 0.001

    def test_ttl_maximum_enforced(self) -> None:
        from predictive.golden_record_generator import _BASE_TTL_HOURS, _compute_expires_at

        expires = _compute_expires_at(0.0, _NOW)
        actual_hours = (expires - _NOW).total_seconds() / 3600
        assert actual_hours == pytest.approx(_BASE_TTL_HOURS, rel=0.01)
