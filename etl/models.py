from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """Output schema returned by the LLM classifier for a single signal."""

    category: Literal["opportunity", "threat", "noise"]
    confidence: float = Field(ge=0.0, le=1.0)
    topic_tags: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "negative", "neutral"]
    urgency: Literal["low", "medium", "high"]
    reasoning: str


NOISE_FALLBACK = ClassificationResult(
    category="noise",
    confidence=0.0,
    topic_tags=[],
    sentiment="neutral",
    urgency="low",
    reasoning="Classification failed — defaulted to noise",
)


class EnrichedSignal(BaseModel):
    """Combined raw event + classification result, ready for DB write."""

    # Raw event fields
    event_id: str
    source: str
    collected_at: datetime
    raw_text: str
    url: str
    author: str
    engagement_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Classification fields
    category: str
    confidence: float
    topic_tags: list[str]
    sentiment: str
    urgency: str
    reasoning: str
    low_confidence: bool  # True when confidence < 0.6; flagged for human review

    enriched_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
