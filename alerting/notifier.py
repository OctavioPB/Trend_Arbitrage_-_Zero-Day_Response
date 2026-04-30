"""Alert notification system — pluggable backends for Slack, webhook, and email."""

from __future__ import annotations

import logging
import os
import smtplib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any

import psycopg2
import requests
from pydantic import BaseModel, Field

from alerting import config as _cfg

logger = logging.getLogger(__name__)

# Fields that must never appear in outbound payloads
_SENSITIVE = ("postgresql://", "sk-ant-", "password", "secret", "bearer ", "smtp_")


class AlertPayload(BaseModel):
    """Canonical alert payload — safe to send to external systems."""

    topic: str
    mpi_score: float
    signal_count: int
    recommended_action: str = ""
    expires_at: datetime
    dashboard_url: str = ""
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    @classmethod
    def from_golden_record(
        cls, record: dict, dashboard_url: str = ""
    ) -> "AlertPayload":
        expires = record["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        return cls(
            topic=record["topic_cluster"],
            mpi_score=float(record.get("mpi_score") or 0.0),
            signal_count=int(record.get("signal_count") or 0),
            recommended_action=record.get("recommended_action") or "",
            expires_at=expires,
            dashboard_url=dashboard_url,
        )

    def model_dump_safe(self) -> dict[str, Any]:
        """Serialize, redacting any value that contains sensitive strings."""
        data = self.model_dump(mode="json")
        for key, val in data.items():
            if any(s in str(val).lower() for s in _SENSITIVE):
                data[key] = "[REDACTED]"
        return data


# ── Backend ABC ───────────────────────────────────────────────────────────────


class AlertBackend(ABC):
    @abstractmethod
    def send(self, payload: AlertPayload) -> None: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


# ── Slack ─────────────────────────────────────────────────────────────────────


class SlackBackend(AlertBackend):
    """Sends rich Block Kit messages via a Slack incoming webhook URL."""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    @property
    def name(self) -> str:
        return "slack"

    def send(self, payload: AlertPayload) -> None:
        now = datetime.now(tz=timezone.utc)
        expires = (
            payload.expires_at
            if payload.expires_at.tzinfo
            else payload.expires_at.replace(tzinfo=timezone.utc)
        )
        ttl_min = max(0, int((expires - now).total_seconds() / 60))

        blocks: list[dict] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Trend Alert — {payload.topic}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*MPI Score:*\n{payload.mpi_score:.3f}"},
                    {"type": "mrkdwn", "text": f"*Signals:*\n{payload.signal_count}"},
                    {"type": "mrkdwn", "text": f"*Expires in:*\n{ttl_min} min"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Action:*\n{payload.recommended_action or '—'}",
                    },
                ],
            },
        ]
        if payload.dashboard_url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Dashboard"},
                            "url": payload.dashboard_url,
                            "style": "primary",
                        }
                    ],
                }
            )

        resp = requests.post(self._url, json={"blocks": blocks}, timeout=10)
        resp.raise_for_status()
        logger.info("Slack alert sent for topic %s (mpi=%.3f)", payload.topic, payload.mpi_score)


# ── Generic webhook ───────────────────────────────────────────────────────────


class WebhookBackend(AlertBackend):
    """POSTs the canonical payload as JSON to any URL."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {}

    @property
    def name(self) -> str:
        return "webhook"

    def send(self, payload: AlertPayload) -> None:
        resp = requests.post(
            self._url,
            json=payload.model_dump_safe(),
            headers={"Content-Type": "application/json", **self._headers},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Webhook alert sent for topic %s to %s", payload.topic, self._url)


# ── Email (SMTP) ──────────────────────────────────────────────────────────────


class EmailBackend(AlertBackend):
    """Sends a plain-text alert via SMTP with STARTTLS."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
        to_addrs: list[str],
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from_addr = from_addr
        self._to_addrs = to_addrs

    @property
    def name(self) -> str:
        return "email"

    def send(self, payload: AlertPayload) -> None:
        body = (
            f"Trend Alert — {payload.topic}\n\n"
            f"MPI Score:  {payload.mpi_score:.3f}\n"
            f"Signals:    {payload.signal_count}\n"
            f"Action:     {payload.recommended_action or '—'}\n"
            f"Expires at: {payload.expires_at.isoformat()}\n"
        )
        if payload.dashboard_url:
            body += f"\nDashboard:  {payload.dashboard_url}\n"

        msg = MIMEText(body)
        msg["Subject"] = f"[Trend Alert] {payload.topic} — MPI {payload.mpi_score:.3f}"
        msg["From"] = self._from_addr
        msg["To"] = ", ".join(self._to_addrs)

        with smtplib.SMTP(self._host, self._port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(self._user, self._password)
            smtp.sendmail(self._from_addr, self._to_addrs, msg.as_string())

        logger.info(
            "Email alert sent for topic %s to %s", payload.topic, self._to_addrs
        )


# ── Backend factory ───────────────────────────────────────────────────────────


def build_backend(channel: dict) -> AlertBackend | None:
    """Instantiate the correct backend from a channel config dict."""
    ctype = channel.get("type", "")
    try:
        if ctype == "slack":
            return SlackBackend(webhook_url=channel["webhook_url"])
        if ctype == "webhook":
            return WebhookBackend(url=channel["url"], headers=channel.get("headers"))
        if ctype == "email":
            return EmailBackend(
                host=channel["smtp_host"],
                port=int(channel.get("smtp_port", 587)),
                user=channel["smtp_user"],
                password=channel["smtp_password"],
                from_addr=channel["from_addr"],
                to_addrs=channel["to_addrs"],
            )
    except KeyError as exc:
        logger.error("Channel config for type %r is missing required key: %s", ctype, exc)
        return None
    logger.warning("Unknown channel type %r — skipping", ctype)
    return None


# ── AlertNotifier ─────────────────────────────────────────────────────────────


class AlertNotifier:
    """Loads matching rules from DB and dispatches notifications for a Golden Record.

    Backend failures are caught individually — one failing backend never blocks others.
    """

    def __init__(self, dashboard_url: str = "", dsn: str = "") -> None:
        self._dashboard_url = dashboard_url or os.environ.get("DASHBOARD_URL", "")
        self._dsn = dsn or os.environ.get(
            "POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage"
        )

    def fire(self, golden_record: dict) -> None:
        """Evaluate all matching alert rules and dispatch notifications.

        Args:
            golden_record: dict with keys topic_cluster, mpi_score, signal_count,
                           recommended_action, expires_at.
        """
        topic = golden_record.get("topic_cluster", "")
        mpi = float(golden_record.get("mpi_score") or 0.0)

        try:
            with psycopg2.connect(self._dsn) as conn:
                rules = _cfg.get_matching_rules(conn, topic, mpi)
        except Exception as exc:
            logger.error("Failed to load alert rules (topic=%r): %s", topic, exc)
            return

        if not rules:
            logger.debug("No matching alert rules for topic %r (mpi=%.3f)", topic, mpi)
            return

        payload = AlertPayload.from_golden_record(golden_record, self._dashboard_url)

        for rule in rules:
            backends = [
                b for ch in rule.channels if (b := build_backend(ch)) is not None
            ]
            if not backends:
                logger.debug("Rule %s has no valid backends — skipping", rule.id)
                continue

            fired = False
            for backend in backends:
                try:
                    backend.send(payload)
                    fired = True
                except Exception as exc:
                    logger.error(
                        "Backend %s failed for rule %s (topic=%r): %s",
                        backend.name,
                        rule.id,
                        topic,
                        exc,
                    )

            if fired:
                try:
                    with psycopg2.connect(self._dsn) as conn:
                        _cfg.update_last_alerted(conn, rule.id)
                except Exception as exc:
                    logger.error(
                        "Failed to stamp suppression clock for rule %s: %s", rule.id, exc
                    )
