"""Slack escalation action — pages a human reviewer for high-confidence signals.

Reuses SLACK_WEBHOOK_URL from F1 alerting. The message is distinct from the
automated F1 alerts: it explicitly requests a human decision, not just awareness.

In dry_run mode: returns the intended Block Kit payload without sending.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10


def execute(config: dict, golden_record: dict, dry_run: bool = False) -> dict:
    """Send a Slack escalation message requesting human review.

    Returns a result dict — never raises.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    dashboard_url = os.environ.get("DASHBOARD_URL", "")

    payload = _build_blocks(golden_record, dashboard_url)

    if dry_run:
        return {
            "type": "slack_escalation",
            "success": True,
            "dry_run": True,
            "detail": f"DRY RUN — would POST escalation to {webhook_url or '[SLACK_WEBHOOK_URL not set]'}",
            "payload": payload,
        }

    if not webhook_url:
        return {
            "type": "slack_escalation",
            "success": False,
            "dry_run": False,
            "detail": "SLACK_WEBHOOK_URL is not configured",
            "error": "missing env var",
        }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        logger.info(
            "Slack escalation sent: topic=%r mpi=%.3f",
            golden_record.get("topic_cluster"),
            golden_record.get("mpi_score", 0.0),
        )
        return {
            "type": "slack_escalation",
            "success": True,
            "dry_run": False,
            "detail": "Escalation delivered to Slack",
        }
    except requests.RequestException as exc:
        logger.error("Slack escalation failed: %s", exc)
        return {
            "type": "slack_escalation",
            "success": False,
            "dry_run": False,
            "detail": "Slack escalation failed",
            "error": str(exc)[:200],
        }


def _build_blocks(golden_record: dict, dashboard_url: str) -> dict:
    topic = golden_record.get("topic_cluster", "unknown")
    mpi = float(golden_record.get("mpi_score") or 0.0)
    signal_count = int(golden_record.get("signal_count") or 0)
    action = golden_record.get("recommended_action", "")
    expires_at = golden_record.get("expires_at", "")

    header = f":rotating_light: *Human Review Required — {topic}*"
    body = (
        f"*MPI Score:* `{mpi:.3f}`  |  *Signals:* `{signal_count}`\n"
        f"*Action:* {action}\n"
        f"*Expires:* {expires_at}"
    )

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_This playbook requires a human decision._"},
        },
    ]

    if dashboard_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Dashboard"},
                        "url": dashboard_url,
                        "style": "primary",
                    }
                ],
            }
        )

    return {"blocks": blocks}
