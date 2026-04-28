"""Market Pressure Index calculator.

Formula (weights configurable via config/mpi_weights.json):
    MPI = volume * 0.4 + velocity * 0.35 + sentiment * 0.25

    volume_score    = signals_in_window / baseline_avg_signals          [clamped 0–1]
    velocity_score  = (signals_last_15min / signals_prev_15min) - 1     [clamped 0–1]
    sentiment_score = proportion of 'positive' signals in window        [0–1]

Weights are reloaded from disk on every call so changes take effect
without a restart.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_WEIGHTS_PATH = Path(os.environ.get("MPI_WEIGHTS_PATH", "config/mpi_weights.json"))
_VELOCITY_WINDOW_MINUTES = 15
_MIN_SIGNALS = 1  # clusters below this skip velocity (not enough data)


class MPIResult(BaseModel):
    """All scores and metadata from a single MPI computation."""

    topic_cluster: str
    mpi_score: float = Field(ge=0.0, le=1.0)
    volume_score: float = Field(ge=0.0, le=1.0)
    velocity_score: float = Field(ge=0.0, le=1.0)
    sentiment_score: float = Field(ge=0.0, le=1.0)
    signal_count: int
    baseline_avg_signals: float
    weights: dict[str, float]
    computed_at: datetime


def load_weights() -> dict[str, float]:
    """Load MPI weights from config/mpi_weights.json.

    Reloads from disk on every call — weight changes take effect immediately.
    """
    try:
        raw = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
        weights = {k: float(v) for k, v in raw.items() if not k.startswith("_")}
    except FileNotFoundError:
        logger.warning("%s not found — using hardcoded defaults", _WEIGHTS_PATH)
        weights = {"volume": 0.4, "velocity": 0.35, "sentiment": 0.25}
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Invalid weights file: %s — using hardcoded defaults", exc)
        weights = {"volume": 0.4, "velocity": 0.35, "sentiment": 0.25}

    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        logger.warning("MPI weights sum to %.3f (expected 1.0) — scores may exceed 1.0", total)

    return weights


def calculate_mpi(
    signals: list[dict],
    topic_cluster: str = "",
    baseline_avg_signals: float = 10.0,
    window_minutes: int = 60,
    now: datetime | None = None,
    weights: dict[str, float] | None = None,
) -> MPIResult:
    """Compute the Market Pressure Index for a list of enriched signal dicts.

    Args:
        signals:              Enriched signal dicts in the rolling window.
                              Each dict must have 'collected_at' (datetime or ISO str)
                              and 'sentiment' ('positive'|'negative'|'neutral').
        topic_cluster:        Label for the cluster (for logging/result).
        baseline_avg_signals: Average signals per equivalent window (historical).
                              Used to compute volume_score. Must be >= 0.
        window_minutes:       Width of the rolling window in minutes.
        now:                  Reference time (defaults to utcnow). Pass a fixed value
                              in tests to avoid flakiness.
        weights:              Override weights dict. If None, loads from disk.

    Returns:
        MPIResult with all component scores clamped to [0.0, 1.0].
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    if weights is None:
        weights = load_weights()

    w_vol = weights.get("volume", 0.4)
    w_vel = weights.get("velocity", 0.35)
    w_sen = weights.get("sentiment", 0.25)

    # Normalize collected_at to tz-aware datetimes
    normalized = _normalize_signals(signals, now, window_minutes)

    volume_score = _compute_volume(len(normalized), baseline_avg_signals)
    velocity_score = _compute_velocity(normalized, now)
    sentiment_score = _compute_sentiment(normalized)

    mpi = (w_vol * volume_score) + (w_vel * velocity_score) + (w_sen * sentiment_score)
    mpi = min(max(mpi, 0.0), 1.0)

    logger.info(
        "MPI cluster=%r score=%.3f volume=%.3f velocity=%.3f sentiment=%.3f "
        "signals=%d baseline=%.1f",
        topic_cluster,
        mpi,
        volume_score,
        velocity_score,
        sentiment_score,
        len(normalized),
        baseline_avg_signals,
    )

    return MPIResult(
        topic_cluster=topic_cluster,
        mpi_score=round(mpi, 3),
        volume_score=round(volume_score, 3),
        velocity_score=round(velocity_score, 3),
        sentiment_score=round(sentiment_score, 3),
        signal_count=len(normalized),
        baseline_avg_signals=baseline_avg_signals,
        weights=weights,
        computed_at=now,
    )


# ── private helpers ───────────────────────────────────────────────────────────


def _as_aware_dt(value: Any) -> datetime:
    """Convert ISO string or datetime to timezone-aware datetime."""
    if isinstance(value, str):
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raise TypeError(f"Cannot convert {type(value)} to datetime")


def _normalize_signals(
    signals: list[dict],
    now: datetime,
    window_minutes: int,
) -> list[dict]:
    """Return signals that fall within the window, with datetime-normalized collected_at."""
    cutoff = now - timedelta(minutes=window_minutes)
    result = []
    for s in signals:
        try:
            dt = _as_aware_dt(s["collected_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if dt >= cutoff:
            result.append({**s, "collected_at": dt})
    return result


def _compute_volume(signal_count: int, baseline: float) -> float:
    if baseline <= 0:
        return 1.0 if signal_count > 0 else 0.0
    return min(signal_count / baseline, 1.0)


def _compute_velocity(signals: list[dict], now: datetime) -> float:
    if not signals:
        return 0.0

    last_cutoff = now - timedelta(minutes=_VELOCITY_WINDOW_MINUTES)
    prev_cutoff = last_cutoff - timedelta(minutes=_VELOCITY_WINDOW_MINUTES)

    last_15 = sum(1 for s in signals if s["collected_at"] >= last_cutoff)
    prev_15 = sum(1 for s in signals if prev_cutoff <= s["collected_at"] < last_cutoff)

    if prev_15 == 0:
        # New trend with no prior window: max velocity if activity present, else zero.
        return 1.0 if last_15 > 0 else 0.0

    raw = (last_15 / prev_15) - 1.0
    return min(max(raw, 0.0), 1.0)


def _compute_sentiment(signals: list[dict]) -> float:
    if not signals:
        return 0.0
    positive = sum(1 for s in signals if s.get("sentiment") == "positive")
    return positive / len(signals)
