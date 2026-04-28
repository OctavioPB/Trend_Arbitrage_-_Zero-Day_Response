from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

_EVENT_NS = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")


class RawEvent(BaseModel):
    """Single raw signal published to the raw_signals Kafka topic."""

    event_id: str
    source: Literal["reddit", "twitter", "scraper"]
    collected_at: datetime
    raw_text: str
    url: str
    author: str
    engagement_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_kafka_payload(self) -> dict[str, Any]:
        """JSON-compatible dict for Kafka serialization."""
        return self.model_dump(mode="json")


def make_event_id(source: str, content_key: str) -> str:
    """Deterministic UUID5 so re-running a producer never duplicates the same content."""
    return str(uuid.uuid5(_EVENT_NS, f"{source}:{content_key}"))
