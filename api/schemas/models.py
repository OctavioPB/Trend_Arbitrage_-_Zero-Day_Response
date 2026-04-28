"""Pydantic response models for all API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field


class SignalResponse(BaseModel):
    id: str
    event_id: str
    source: str
    collected_at: datetime
    enriched_at: datetime | None = None
    category: str
    confidence: float
    topic_tags: list[str] = Field(default_factory=list)
    sentiment: str
    urgency: str
    engagement_score: float
    url: str = ""
    reasoning: str = ""
    low_confidence: bool = False


class SignalListResponse(BaseModel):
    signals: list[SignalResponse]
    total: int
    page: int
    page_size: int


class MPICell(BaseModel):
    """One cell in the heat map: a (topic_cluster, time_bucket) pair."""

    topic_cluster: str
    time_bucket: datetime
    score: float = Field(ge=0.0, le=1.0)
    signal_count: int
    sentiment_score: float = Field(ge=0.0, le=1.0)


class MPIGridResponse(BaseModel):
    computed_at: datetime
    window_minutes: int
    cells: list[MPICell]
    topic_clusters: list[str]
    time_buckets: list[datetime]


class GoldenRecordResponse(BaseModel):
    id: str
    created_at: datetime
    topic_cluster: str
    mpi_score: float
    signal_count: int
    audience_proxy: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str = ""
    expires_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def ttl_seconds(self) -> int:
        """Seconds remaining until this record expires."""
        from datetime import timezone

        now = datetime.now(tz=timezone.utc)
        expires = (
            self.expires_at
            if self.expires_at.tzinfo
            else self.expires_at.replace(tzinfo=timezone.utc)
        )
        return max(0, int((expires - now).total_seconds()))


class GoldenRecordListResponse(BaseModel):
    records: list[GoldenRecordResponse]
    total: int
