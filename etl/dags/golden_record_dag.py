"""Golden record DAG — runs every 5 minutes.

Pipeline:
  compute_mpi → archive_mpi → generate_golden_records → fire_alerts → sync_audiences

For each MPI computation cycle:
  - compute_mpi computes MPI for ALL active topic clusters and returns
    both the full results list and the triggered (above-threshold) subset.
  - archive_mpi persists all results to mpi_history (idempotent upsert).
  - generate_golden_records writes golden_records rows and publishes to Kafka
    for triggered clusters only.
  - fire_alerts dispatches Slack/webhook/email notifications via alert rules.
  - sync_audiences pushes audience definitions to Google Ads and Meta.
    Platform failures are logged to audience_sync_log and do not crash the DAG.
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
    def compute_mpi() -> dict:
        """Compute MPI for all active clusters.

        Returns dict with:
          all_results: list of MPIResult dicts for every cluster computed
          triggered:   subset where mpi_score >= MPI_THRESHOLD
        """
        import os

        from predictive.threshold_monitor import (
            MPI_THRESHOLD,
            SIGNAL_WINDOW_MINUTES,
            compute_all_mpi,
        )

        all_results = compute_all_mpi(window_minutes=SIGNAL_WINDOW_MINUTES)
        threshold = float(os.environ.get("MPI_THRESHOLD", str(MPI_THRESHOLD)))
        triggered = [r for r in all_results if r["mpi_score"] >= threshold]

        logger.info(
            "compute_mpi: %d total cluster(s), %d triggered",
            len(all_results),
            len(triggered),
        )
        return {"all_results": all_results, "triggered": triggered}

    @task()
    def archive_mpi(mpi_output: dict) -> None:
        """Persist all cluster MPI scores to mpi_history (idempotent upsert)."""
        all_results = mpi_output.get("all_results") or []
        if not all_results:
            logger.info("archive_mpi: no results to persist")
            return

        from predictive.mpi_archiver import archive_results

        written = archive_results(all_results)
        logger.info("archive_mpi: wrote %d row(s) to mpi_history", written)

    @task()
    def generate_golden_records(mpi_output: dict) -> list[dict]:
        """Generate and persist a golden record for each triggered cluster."""
        triggered_clusters = mpi_output.get("triggered") or []
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

    @task()
    def sync_audiences(golden_records: list[dict]) -> None:
        """Push each golden record's audience to Google Ads and Meta.

        Platform failures are caught, logged to audience_sync_log with
        status='error', and do not raise — so one failing platform never
        blocks the other or rolls back the golden record.
        """
        if not golden_records:
            return

        import os

        import psycopg2

        from integrations._sync_log import already_synced, write_sync_log
        from integrations.audience_mapper import load_mapping, map_audience
        from integrations.google_ads import GoogleAdsAudienceSync
        from integrations.meta_ads import MetaAudienceSync

        dsn = os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )
        mapping = load_mapping()
        google_sync = GoogleAdsAudienceSync()
        meta_sync = MetaAudienceSync()

        with psycopg2.connect(dsn) as conn:
            for record in golden_records:
                record_id: str = record.get("id", "")
                if not record_id:
                    logger.warning("sync_audiences: skipping record with no id")
                    continue

                audience_proxy = record.get("audience_proxy") or {}
                topic_cluster = record.get("topic_cluster", "")
                spec = map_audience(audience_proxy, topic_cluster, mapping)

                _sync_one_platform(conn, record_id, "google_ads", google_sync, spec)
                _sync_one_platform(conn, record_id, "meta", meta_sync, spec)

    def _sync_one_platform(conn, record_id: str, platform: str, syncer, spec) -> None:
        """Attempt a single platform sync and write the result to audience_sync_log."""
        from integrations._sync_log import already_synced, write_sync_log

        if already_synced(conn, record_id, platform):
            logger.info(
                "sync_audiences: %s already synced for golden_record_id=%s — skipping",
                platform,
                record_id,
            )
            return

        try:
            audience_id = syncer.sync(record_id, spec)
            if audience_id is None:
                # Sync returned None → platform disabled
                write_sync_log(conn, record_id, platform, "skipped")
            else:
                write_sync_log(conn, record_id, platform, "success", audience_id=audience_id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "sync_audiences: %s failed for golden_record_id=%s: %s",
                platform,
                record_id,
                exc,
            )
            write_sync_log(conn, record_id, platform, "error", error_message=str(exc))
        finally:
            conn.commit()

    mpi_output = compute_mpi()
    archive_mpi(mpi_output)
    records = generate_golden_records(mpi_output)
    fire_alerts(records)
    sync_audiences(records)


golden_record_dag()
