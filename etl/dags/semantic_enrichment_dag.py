"""Semantic enrichment DAG — runs every 5 minutes.

Pipeline:
  consume_raw → deduplicate → classify → [write_db, publish_enriched]

Reads raw events from the raw_signals Kafka topic, enriches them with LLM
classification, writes to enriched_signals table, and republishes to the
enriched_signals Kafka topic for downstream consumers.
"""

import json
import logging
import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

KAFKA_BATCH_SIZE: int = int(os.environ.get("ETL_KAFKA_BATCH_SIZE", "100"))
CONSUMER_GROUP: str = "semantic-enrichment-etl"

_DEFAULT_ARGS = {
    "owner": "trend-arbitrage",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=8),
}


@dag(
    dag_id="semantic_enrichment",
    schedule="*/5 * * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["etl", "ingestion"],
    doc_md=__doc__,
)
def semantic_enrichment_dag() -> None:

    @task()
    def consume_raw() -> list[dict]:
        """Read up to KAFKA_BATCH_SIZE events from raw_signals topic."""
        from ingestion.config.kafka_config import TOPIC_RAW, create_consumer

        consumer = create_consumer(
            group_id=CONSUMER_GROUP,
            topics=[TOPIC_RAW],
            auto_offset_reset="earliest",
        )
        events: list[dict] = []
        try:
            for message in consumer:
                try:
                    events.append(json.loads(message.value))
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Skipping non-JSON message at partition=%d offset=%d: %s",
                        message.partition,
                        message.offset,
                        exc,
                    )
                if len(events) >= KAFKA_BATCH_SIZE:
                    break
        finally:
            consumer.close()

        logger.info("Consumed %d raw events from Kafka", len(events))
        return events

    @task()
    def deduplicate(events: list[dict]) -> list[dict]:
        """Filter events already present in enriched_signals."""
        from etl.tasks.deduplicator import filter_new_events

        return filter_new_events(events)

    @task()
    def classify(events: list[dict]) -> list[dict]:
        """Batch-classify events with the LLM. Returns enriched signal dicts."""
        if not events:
            logger.info("No new events to classify")
            return []
        from etl.tasks.llm_classifier import classify_batch_sync

        return classify_batch_sync(events)

    @task()
    def write_db(enriched: list[dict]) -> int:
        """Insert enriched signals into PostgreSQL."""
        if not enriched:
            return 0
        from etl.tasks.db_writer import write_enriched_signals

        return write_enriched_signals(enriched)

    @task()
    def publish_enriched(enriched: list[dict]) -> None:
        """Republish enriched signals to the enriched_signals Kafka topic."""
        if not enriched:
            return
        from ingestion.config.kafka_config import TOPIC_ENRICHED, create_producer, publish_with_retry

        producer = create_producer()
        for signal in enriched:
            publish_with_retry(producer, TOPIC_ENRICHED, signal, key=signal.get("event_id"))
        logger.info("Published %d enriched signals to Kafka", len(enriched))

    # ── wiring ────────────────────────────────────────────────────────────────
    raw = consume_raw()
    deduped = deduplicate(raw)
    classified = classify(deduped)
    write_db(classified)
    publish_enriched(classified)


semantic_enrichment_dag()
