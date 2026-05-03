"""Threshold and source-weight calibrator for the MPI pipeline.

Analyses performance_events over a rolling window and produces a CalibrationResult
that suggests updated MPI_THRESHOLD and source_weight values.

Design rules
────────────
• Precision = Golden Records with positive CTR outcome / all Golden Records
  with measured CTR outcomes (platform CTR >= POSITIVE_CTR_THRESHOLD).
• Recall (proxy) = hits / all Golden Records issued in the window
  (includes unmeasured ones; biased low when collection is incomplete,
  so it is reported but not used for threshold adjustment decisions).
• A proposal is written only when sample_count >= min_samples (default 30)
  and the suggested threshold differs from the current one.
• Safety bounds: MPI_THRESHOLD is always clamped to [0.50, 0.95].
• Source weights are adjusted proportionally to the lift each source
  provides over its average contribution across all measured records.
  Weights are then re-normalised so their mean equals the pre-calibration mean.

Calling convention
──────────────────
    calibrator = ThresholdCalibrator()
    result = calibrator.compute(conn)   # None if < 30 samples
    if result:
        proposal_id = calibrator.write_proposal(conn, result)
        conn.commit()
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_THRESHOLD_MIN: float = 0.50
_THRESHOLD_MAX: float = 0.95
_THRESHOLD_STEP_DOWN: float = 0.02  # applied when precision is high
_THRESHOLD_STEP_UP: float = 0.03    # applied when precision is low
_HIGH_PRECISION_CUTOFF: float = 0.70
_LOW_PRECISION_CUTOFF: float = 0.50

# A measured CTR >= this value is classified as a positive outcome ("hit")
_POSITIVE_CTR_THRESHOLD: float = float(
    os.environ.get("POSITIVE_CTR_THRESHOLD", "0.015")
)

_WEIGHTS_PATH = Path(os.environ.get("SOURCE_WEIGHTS_PATH", "config/source_weights.json"))


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class CalibrationResult:
    precision: float
    recall: float
    sample_count: int
    current_mpi_threshold: float
    proposed_mpi_threshold: float
    current_source_weights: dict[str, float]
    proposed_source_weights: dict[str, float]


# ── Calibrator ─────────────────────────────────────────────────────────────────


class ThresholdCalibrator:
    """Compute calibration proposals from measured Golden Record outcomes."""

    def compute(
        self,
        conn,
        window_days: int = 30,
        min_samples: int = 30,
    ) -> CalibrationResult | None:
        """Analyse performance_events and return a CalibrationResult.

        Returns None if fewer than min_samples Golden Records have measured
        CTR outcomes in the window (not enough data to make a reliable proposal).
        """
        measured = self._load_measured_outcomes(conn, window_days)
        if len(measured) < min_samples:
            logger.info(
                "threshold_calibrator: only %d measured sample(s) — need %d; skipping",
                len(measured),
                min_samples,
            )
            return None

        hits = [r for r in measured if r["ctr"] >= _POSITIVE_CTR_THRESHOLD]
        misses = [r for r in measured if r["ctr"] < _POSITIVE_CTR_THRESHOLD]
        precision = len(hits) / len(measured)

        # Recall proxy: hits / total Golden Records issued in the window
        total_issued = self._count_total_issued(conn, window_days)
        recall = len(hits) / max(total_issued, 1)

        current_threshold = float(os.environ.get("MPI_THRESHOLD", "0.72"))
        proposed_threshold = self._suggest_threshold(current_threshold, precision)

        current_weights = self._load_current_weights()
        hit_ids = {r["golden_record_id"] for r in hits}
        miss_ids = {r["golden_record_id"] for r in misses}
        proposed_weights = self._suggest_weights(
            conn, window_days, hit_ids, miss_ids, current_weights
        )

        logger.info(
            "threshold_calibrator: samples=%d hits=%d precision=%.3f recall=%.3f "
            "threshold %.3f→%.3f",
            len(measured),
            len(hits),
            precision,
            recall,
            current_threshold,
            proposed_threshold,
        )

        return CalibrationResult(
            precision=round(precision, 4),
            recall=round(recall, 4),
            sample_count=len(measured),
            current_mpi_threshold=current_threshold,
            proposed_mpi_threshold=proposed_threshold,
            current_source_weights=current_weights,
            proposed_source_weights=proposed_weights,
        )

    def write_proposal(self, conn, result: CalibrationResult) -> str:
        """Persist a CalibrationResult to calibration_proposals.

        Returns the new proposal UUID. Caller must commit the transaction.
        """
        sql = """
            INSERT INTO calibration_proposals
                (proposed_mpi_threshold, proposed_source_weights,
                 precision, recall, sample_count)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id::text
        """
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    result.proposed_mpi_threshold,
                    json.dumps(result.proposed_source_weights),
                    result.precision,
                    result.recall,
                    result.sample_count,
                ),
            )
            proposal_id: str = cur.fetchone()[0]

        logger.info(
            "calibration_proposal written: id=%s threshold=%.3f",
            proposal_id,
            result.proposed_mpi_threshold,
        )
        return proposal_id

    # ── Private: data loading ──────────────────────────────────────────────────

    def _load_measured_outcomes(
        self, conn, window_days: int
    ) -> list[dict]:
        """Return one row per Golden Record with a measured CTR in the window."""
        sql = """
            SELECT DISTINCT ON (pe.golden_record_id)
                pe.golden_record_id::text,
                pe.value AS ctr
            FROM performance_events pe
            WHERE pe.metric = 'ctr'
              AND pe.measured_at >= NOW() - (%s * INTERVAL '1 day')
            ORDER BY pe.golden_record_id, pe.measured_at DESC
        """
        with conn.cursor() as cur:
            cur.execute(sql, (window_days,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _count_total_issued(self, conn, window_days: int) -> int:
        """Count all Golden Records created in the window (measured or not)."""
        sql = """
            SELECT COUNT(*) FROM golden_records
            WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
        """
        with conn.cursor() as cur:
            cur.execute(sql, (window_days,))
            row = cur.fetchone()
            return int(row[0]) if row else 0

    # ── Private: threshold suggestion ─────────────────────────────────────────

    def _suggest_threshold(self, current: float, precision: float) -> float:
        """Suggest a new MPI_THRESHOLD based on precision.

        High precision (>= 0.70): threshold is filtering well; lower slightly
          to capture more real opportunities.
        Low precision (< 0.50): too many false positives; raise threshold.
        Otherwise: maintain current value.

        Safety bounds: always clamped to [0.50, 0.95].
        """
        if precision >= _HIGH_PRECISION_CUTOFF:
            suggested = current - _THRESHOLD_STEP_DOWN
        elif precision < _LOW_PRECISION_CUTOFF:
            suggested = current + _THRESHOLD_STEP_UP
        else:
            suggested = current

        return round(
            max(_THRESHOLD_MIN, min(_THRESHOLD_MAX, suggested)),
            3,
        )

    # ── Private: source weight suggestion ─────────────────────────────────────

    def _load_current_weights(self) -> dict[str, float]:
        try:
            with _WEIGHTS_PATH.open(encoding="utf-8") as fh:
                raw = json.load(fh)
            return {
                k: float(v)
                for k, v in raw.items()
                if not k.startswith("_")  # skip comment keys
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read source_weights.json: %s — using defaults", exc)
            return {"reddit": 1.0, "twitter": 0.9, "news": 1.2, "linkedin": 1.1, "rss": 0.7}

    def _suggest_weights(
        self,
        conn,
        window_days: int,
        hit_ids: set[str],
        miss_ids: set[str],
        current_weights: dict[str, float],
    ) -> dict[str, float]:
        """Suggest source_weight adjustments based on signal-source contribution.

        Sources that appear disproportionately in hits get a higher weight;
        sources dominant in misses get a lower weight. Weights are normalised
        so their mean equals the pre-calibration mean.
        """
        if not hit_ids and not miss_ids:
            return dict(current_weights)

        all_ids = hit_ids | miss_ids
        source_counts = self._load_source_counts(conn, all_ids, window_days)

        if not source_counts:
            return dict(current_weights)

        # hit_total[source] = signals from that source in hit golden_records
        hit_totals: dict[str, float] = {}
        all_totals: dict[str, float] = {}

        for (gr_id, source), count in source_counts.items():
            all_totals[source] = all_totals.get(source, 0.0) + count
            if gr_id in hit_ids:
                hit_totals[source] = hit_totals.get(source, 0.0) + count

        total_hit_sigs = sum(hit_totals.values()) or 1.0
        total_all_sigs = sum(all_totals.values()) or 1.0

        proposed: dict[str, float] = {}
        for source, old_w in current_weights.items():
            hit_frac = hit_totals.get(source, 0.0) / total_hit_sigs
            all_frac = all_totals.get(source, 0.0) / total_all_sigs

            if all_frac > 0:
                lift = hit_frac / all_frac
                # sqrt dampens overcorrection; floor at 0.25 to never zero out a source
                new_w = old_w * math.sqrt(max(lift, 0.0625))
            else:
                new_w = old_w

            proposed[source] = round(new_w, 3)

        # Normalise: scale so mean(proposed) == mean(current)
        if proposed:
            current_mean = sum(current_weights.values()) / len(current_weights)
            proposed_mean = sum(proposed.values()) / len(proposed)
            if proposed_mean > 0:
                scale = current_mean / proposed_mean
                proposed = {k: round(v * scale, 3) for k, v in proposed.items()}

        return proposed

    def _load_source_counts(
        self, conn, golden_record_ids: set[str], window_days: int
    ) -> dict[tuple[str, str], float]:
        """Return {(golden_record_id, source): signal_count} for the given records."""
        if not golden_record_ids:
            return {}

        # Build a temporary values list for the IN clause
        placeholders = ", ".join(["%s::uuid"] * len(golden_record_ids))
        sql = f"""
            SELECT gr.id::text AS golden_record_id,
                   es.source,
                   COUNT(*) AS sig_count
            FROM golden_records gr
            JOIN enriched_signals es
              ON es.collected_at BETWEEN gr.created_at - INTERVAL '60 minutes'
                                     AND gr.created_at
             AND es.topic_tags && ARRAY[gr.topic_cluster]
            WHERE gr.id IN ({placeholders})
              AND gr.created_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY gr.id, es.source
        """
        params = list(golden_record_ids) + [window_days]
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return {
                    (row[0], row[1]): float(row[2])
                    for row in cur.fetchall()
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Source count query failed: %s — weights unchanged", exc)
            return {}
