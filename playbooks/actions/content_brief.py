"""Content brief action — POST a structured content brief to a webhook.

Webhook URL is read from CONTENT_BRIEF_WEBHOOK_URL. If the env var is not set
the action returns success=False with a clear message (not an exception) so the
engine can continue to subsequent actions.

In dry_run mode: returns the intended payload without sending any HTTP request.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds


def execute(config: dict, golden_record: dict, dry_run: bool = False) -> dict:
    """Post a content brief for the triggered topic cluster.

    Returns a result dict — never raises.
    """
    webhook_url = os.environ.get("CONTENT_BRIEF_WEBHOOK_URL", "")

    payload = _build_payload(config, golden_record)

    if dry_run:
        return {
            "type": "content_brief",
            "success": True,
            "dry_run": True,
            "detail": f"DRY RUN — would POST content brief to {webhook_url or '[CONTENT_BRIEF_WEBHOOK_URL not set]'}",
            "payload": payload,
        }

    if not webhook_url:
        return {
            "type": "content_brief",
            "success": False,
            "dry_run": False,
            "detail": "CONTENT_BRIEF_WEBHOOK_URL is not configured",
            "error": "missing env var",
        }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        logger.info(
            "Content brief sent: topic=%r mpi=%.3f status=%d",
            golden_record.get("topic_cluster"),
            golden_record.get("mpi_score", 0.0),
            resp.status_code,
        )
        return {
            "type": "content_brief",
            "success": True,
            "dry_run": False,
            "detail": f"Content brief delivered (HTTP {resp.status_code})",
        }
    except requests.RequestException as exc:
        logger.error("Content brief failed: %s", exc)
        return {
            "type": "content_brief",
            "success": False,
            "dry_run": False,
            "detail": "Content brief delivery failed",
            "error": str(exc)[:200],
        }


def _build_payload(config: dict, golden_record: dict) -> dict:
    topic = golden_record.get("topic_cluster", "")
    mpi = golden_record.get("mpi_score", 0.0)
    audience = golden_record.get("audience_proxy") or {}

    return {
        "topic_cluster": topic,
        "mpi_score": round(float(mpi), 3),
        "signal_count": int(golden_record.get("signal_count") or 0),
        "recommended_action": golden_record.get("recommended_action", ""),
        "expires_at": golden_record.get("expires_at", ""),
        "angle": _derive_angle(mpi),
        "urgency": _derive_urgency(mpi),
        "audience_hints": {
            "subreddits": (audience.get("subreddits") or [])[:5],
            "top_topics": (audience.get("top_topics") or [])[:10],
            "handles": (audience.get("handles") or [])[:5],
        },
    }


def _derive_angle(mpi: float) -> str:
    if mpi >= 0.9:
        return "breaking"
    if mpi >= 0.8:
        return "emerging-trend"
    return "opportunity"


def _derive_urgency(mpi: float) -> str:
    if mpi >= 0.9:
        return "high"
    if mpi >= 0.75:
        return "medium"
    return "low"
