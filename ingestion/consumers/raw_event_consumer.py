"""Raw event consumer — reads from raw_signals for verification and logging only.

This consumer is NOT in the ETL path. Airflow DAGs handle enrichment.
Use this to confirm producers are publishing well-formed events.
"""

import json
import logging
import os

from kafka import KafkaConsumer
from pydantic import ValidationError

from ingestion.config.kafka_config import TOPIC_RAW, create_consumer
from ingestion.models import RawEvent

logger = logging.getLogger(__name__)


class RawEventConsumer:
    """Consumes raw_signals and logs each event. Intended for local verification."""

    def __init__(self, group_id: str = "raw-event-verifier") -> None:
        self._consumer: KafkaConsumer = create_consumer(
            group_id=group_id,
            topics=[TOPIC_RAW],
            auto_offset_reset="latest",
        )

    def run(self) -> None:
        """Block and process messages until interrupted."""
        logger.info("RawEventConsumer listening on topic '%s' (Ctrl+C to stop)", TOPIC_RAW)
        try:
            for message in self._consumer:
                self._process(message)
        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
        finally:
            self._consumer.close()

    def _process(self, message) -> None:
        try:
            payload = json.loads(message.value)
            event = RawEvent.model_validate(payload)
            logger.info(
                "[partition=%d offset=%d] source=%-8s event_id=%s author=%s engagement=%.0f",
                message.partition,
                message.offset,
                event.source,
                event.event_id,
                event.author or "(none)",
                event.engagement_score,
            )
        except json.JSONDecodeError as exc:
            logger.warning(
                "Non-JSON message at partition=%d offset=%d: %s",
                message.partition,
                message.offset,
                exc,
            )
        except ValidationError as exc:
            logger.warning(
                "Schema mismatch at partition=%d offset=%d: %s",
                message.partition,
                message.offset,
                exc,
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )
    RawEventConsumer().run()
