"""Shared Kafka client factory with retry logic and connection failure handling."""

import json
import logging
import os
from typing import Any

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError, NoBrokersAvailable
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

BOOTSTRAP_SERVERS: str = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_RAW: str = os.environ.get("KAFKA_TOPIC_RAW", "raw_signals")
TOPIC_ENRICHED: str = os.environ.get("KAFKA_TOPIC_ENRICHED", "enriched_signals")


def _serialize(value: Any) -> bytes:
    return json.dumps(value, default=str).encode("utf-8")


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((NoBrokersAvailable, KafkaError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def create_producer() -> KafkaProducer:
    """Return a KafkaProducer, retrying with exponential backoff if the broker is unreachable."""
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS.split(","),
        value_serializer=_serialize,
        acks="all",
        retries=5,
        compression_type="gzip",
    )


def create_consumer(
    group_id: str,
    topics: list[str],
    auto_offset_reset: str = "latest",
) -> KafkaConsumer:
    """Return a KafkaConsumer subscribed to the given topics."""
    return KafkaConsumer(
        *topics,
        bootstrap_servers=BOOTSTRAP_SERVERS.split(","),
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=True,
        value_deserializer=lambda b: b,  # raw bytes; callers deserialize
        consumer_timeout_ms=1000,
    )


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type(KafkaError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def publish_with_retry(
    producer: KafkaProducer,
    topic: str,
    payload: dict[str, Any],
    key: str | None = None,
) -> None:
    """Publish payload to topic, blocking for ack and retrying on KafkaError."""
    key_bytes = key.encode("utf-8") if key else None
    future = producer.send(topic, value=payload, key=key_bytes)
    future.get(timeout=10)
