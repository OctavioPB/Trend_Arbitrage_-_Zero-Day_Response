"""Calibration DAG — runs weekly (Monday 09:00 UTC).

Pipeline:
  collect_performance → compute_calibration

collect_performance:
  Polls Google Ads and Meta for campaign metrics on all Golden Records whose
  audiences were synced by F5. Writes results to performance_events.
  Platform failures are caught and logged without crashing the DAG.

compute_calibration:
  Runs the ThresholdCalibrator over the last 30 days of performance data.
  If >= 30 measured samples exist and the calibration differs from the current
  config, writes a CalibrationProposal row to calibration_proposals for human
  review via POST /performance/apply-proposal/{id}.
  No auto-apply — all changes require explicit operator approval.
"""

import logging
from datetime import timedelta

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

_DEFAULT_ARGS = {
    "owner": "trend-arbitrage",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=30),
}

_MEASUREMENT_WINDOW_HOURS: int = 24
_CALIBRATION_WINDOW_DAYS: int = 30
_MIN_SAMPLES: int = 30


@dag(
    dag_id="performance_calibration",
    schedule="0 9 * * 1",  # weekly, Monday 09:00 UTC
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["calibration", "feedback-loop"],
    doc_md=__doc__,
)
def calibration_dag() -> None:

    @task()
    def collect_performance() -> int:
        """Poll Google Ads and Meta for campaign metrics on synced audiences.

        Returns:
            Number of new performance_events rows written.
        """
        import os

        import psycopg2

        from integrations.performance_collector import PerformanceCollector

        dsn = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        collector = PerformanceCollector()
        written = 0

        with psycopg2.connect(dsn) as conn:
            try:
                written = collector.collect(conn, window_hours=_MEASUREMENT_WINDOW_HOURS)
            except Exception as exc:  # noqa: BLE001
                logger.error("Performance collection failed: %s", exc)

        logger.info("collect_performance: wrote %d new event(s)", written)
        return written

    @task()
    def compute_calibration(events_written: int) -> dict:
        """Run ThresholdCalibrator; write proposal if >= MIN_SAMPLES available.

        Returns:
            Dict summarising the proposal (or {"status": "skipped"} if no proposal
            was written).
        """
        import os

        import psycopg2

        from predictive.threshold_calibrator import ThresholdCalibrator

        dsn = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        calibrator = ThresholdCalibrator()

        with psycopg2.connect(dsn) as conn:
            result = calibrator.compute(
                conn,
                window_days=_CALIBRATION_WINDOW_DAYS,
                min_samples=_MIN_SAMPLES,
            )

            if result is None:
                logger.info("compute_calibration: insufficient samples — no proposal written")
                return {"status": "skipped", "reason": f"fewer than {_MIN_SAMPLES} measured samples"}

            proposal_id = calibrator.write_proposal(conn, result)
            conn.commit()

        summary = {
            "status": "proposed",
            "proposal_id": proposal_id,
            "precision": result.precision,
            "recall": result.recall,
            "sample_count": result.sample_count,
            "current_threshold": result.current_mpi_threshold,
            "proposed_threshold": result.proposed_mpi_threshold,
        }
        logger.info(
            "compute_calibration: proposal written id=%s precision=%.3f threshold %.3f→%.3f",
            proposal_id,
            result.precision,
            result.current_mpi_threshold,
            result.proposed_mpi_threshold,
        )
        return summary

    events = collect_performance()
    compute_calibration(events)


calibration_dag()
