"""Golden record DAG — runs every 5 minutes.

Pipeline:
  compute_mpi → generate_golden_records

For each topic cluster where MPI >= MPI_THRESHOLD:
  - Writes a golden_records row to PostgreSQL (with velocity-based expires_at)
  - Publishes a golden_record_ready event to Kafka
"""

import logging
from datetime import timedelta

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

_DEFAULT_ARGS = {
    "owner": "trend-arbitrage",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=6),
}


@dag(
    dag_id="golden_record",
    schedule="*/5 * * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["predictive"],
    doc_md=__doc__,
)
def golden_record_dag() -> None:

    @task()
    def compute_mpi() -> list[dict]:
        """Query enriched_signals, compute MPI per cluster, return triggered clusters."""
        from predictive.threshold_monitor import get_triggered_clusters

        triggered = get_triggered_clusters()
        logger.info("compute_mpi: %d cluster(s) above threshold", len(triggered))
        return triggered

    @task()
    def generate_golden_records(triggered_clusters: list[dict]) -> list[str]:
        """Generate and persist a golden record for each triggered cluster."""
        if not triggered_clusters:
            logger.info("No clusters above threshold — nothing to generate")
            return []

        from predictive.golden_record_generator import generate_and_persist

        record_ids: list[str] = []
        for cluster_dict in triggered_clusters:
            try:
                record_id = generate_and_persist(cluster_dict)
                record_ids.append(record_id)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to generate golden record for cluster=%r: %s",
                    cluster_dict.get("topic_cluster"),
                    exc,
                )

        logger.info("Generated %d golden record(s)", len(record_ids))
        return record_ids

    triggered = compute_mpi()
    generate_golden_records(triggered)


golden_record_dag()
