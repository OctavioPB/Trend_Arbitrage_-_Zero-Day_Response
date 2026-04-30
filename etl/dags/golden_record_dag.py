"""Golden record DAG — runs every 5 minutes.

Pipeline:
  compute_mpi → generate_golden_records → fire_alerts

For each topic cluster where MPI >= MPI_THRESHOLD:
  - Writes a golden_records row to PostgreSQL (with velocity-based expires_at)
  - Publishes a golden_record_ready event to Kafka
  - Fires alert notifications to all matching alert rules (Slack, webhook, email)
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
    def generate_golden_records(triggered_clusters: list[dict]) -> list[dict]:
        """Generate and persist a golden record for each triggered cluster."""
        if not triggered_clusters:
            logger.info("No clusters above threshold — nothing to generate")
            return []

        from predictive.golden_record_generator import generate_and_persist

        records: list[dict] = []
        for cluster_dict in triggered_clusters:
            try:
                record = generate_and_persist(cluster_dict)
                records.append(record)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to generate golden record for cluster=%r: %s",
                    cluster_dict.get("topic_cluster"),
                    exc,
                )

        logger.info("Generated %d golden record(s)", len(records))
        return records

    @task()
    def fire_alerts(golden_records: list[dict]) -> None:
        """Dispatch alert notifications for each generated golden record."""
        if not golden_records:
            return

        import os

        from alerting.notifier import AlertNotifier

        dashboard_url = os.environ.get("DASHBOARD_URL", "")
        notifier = AlertNotifier(dashboard_url=dashboard_url)

        for record in golden_records:
            try:
                notifier.fire(record)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Alerting failed for golden record id=%s cluster=%r: %s",
                    record.get("id"),
                    record.get("topic_cluster"),
                    exc,
                )

    triggered = compute_mpi()
    records = generate_golden_records(triggered)
    fire_alerts(records)


golden_record_dag()
