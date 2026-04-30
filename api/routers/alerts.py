"""Alerts router — CRUD for alert rules.

Credentials in channel configs (webhook_url, smtp_password, headers with auth)
are scrubbed from responses — they are write-once from the client's perspective.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from alerting.config import AlertRule, create_rule, delete_rule, list_rules
from api.db import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

_VALID_CHANNEL_TYPES = {"slack", "webhook", "email"}
# Keys whose values are redacted in GET responses
_REDACT_KEYS = {"webhook_url", "smtp_password", "password", "headers"}


# ── Request / Response models ─────────────────────────────────────────────────


class AlertRuleCreate(BaseModel):
    topic_cluster: str = Field(
        default="*",
        description="Exact cluster name to watch, or '*' to match all clusters.",
    )
    min_mpi: float = Field(default=0.72, ge=0.0, le=1.0)
    min_signal_count: int = Field(default=1, ge=1)
    suppression_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        description="Minimum minutes between repeated alerts for the same rule.",
    )
    channels: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Channel configs. Examples: "
            '{"type":"slack","webhook_url":"https://hooks.slack.com/..."} | '
            '{"type":"webhook","url":"https://example.com/hook","headers":{"X-Token":"..."}} | '
            '{"type":"email","smtp_host":"smtp.gmail.com","smtp_port":587,'
            '"smtp_user":"...","smtp_password":"...","from_addr":"...","to_addrs":["..."]}'
        ),
    )
    enabled: bool = True


class AlertRuleResponse(BaseModel):
    id: str
    topic_cluster: str
    min_mpi: float
    min_signal_count: int
    suppression_minutes: int
    channels: list[dict[str, Any]]
    enabled: bool
    last_alerted_at: str | None
    created_at: str
    updated_at: str


class AlertRuleListResponse(BaseModel):
    rules: list[AlertRuleResponse]
    total: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=AlertRuleListResponse)
def list_alert_rules() -> AlertRuleListResponse:
    """List all alert rules. Sensitive channel fields are redacted in the response."""
    with get_conn() as conn:
        rules = list_rules(conn)
    return AlertRuleListResponse(
        rules=[_to_response(r) for r in rules],
        total=len(rules),
    )


@router.post("", response_model=AlertRuleResponse, status_code=201)
def create_alert_rule(body: AlertRuleCreate) -> AlertRuleResponse:
    """Create an alert rule. Channel credentials are stored but redacted in responses."""
    _validate_channels(body.channels)
    with get_conn() as conn:
        rule = create_rule(conn, body.model_dump())
    logger.info(
        "Alert rule created: id=%s cluster=%r min_mpi=%.3f",
        rule.id,
        rule.topic_cluster,
        rule.min_mpi,
    )
    return _to_response(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_alert_rule(rule_id: str) -> None:
    """Delete an alert rule by ID."""
    with get_conn() as conn:
        found = delete_rule(conn, rule_id)
    if not found:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    logger.info("Alert rule deleted: id=%s", rule_id)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _validate_channels(channels: list[dict]) -> None:
    for ch in channels:
        if ch.get("type") not in _VALID_CHANNEL_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"channel type must be one of {sorted(_VALID_CHANNEL_TYPES)}, got {ch.get('type')!r}",
            )


def _scrub_channels(channels: list[dict]) -> list[dict]:
    """Remove secrets from channel configs before returning to API clients."""
    result = []
    for ch in channels:
        result.append(
            {
                k: ("[REDACTED]" if k in _REDACT_KEYS else v)
                for k, v in ch.items()
            }
        )
    return result


def _to_response(rule: AlertRule) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=rule.id,
        topic_cluster=rule.topic_cluster,
        min_mpi=rule.min_mpi,
        min_signal_count=rule.min_signal_count,
        suppression_minutes=rule.suppression_minutes,
        channels=_scrub_channels(rule.channels),
        enabled=rule.enabled,
        last_alerted_at=(
            rule.last_alerted_at.isoformat() if rule.last_alerted_at else None
        ),
        created_at=rule.created_at.isoformat(),
        updated_at=rule.updated_at.isoformat(),
    )
