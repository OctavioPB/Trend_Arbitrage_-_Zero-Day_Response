"""Bid adjustment action — increase Google Ads max CPC for campaigns tied to a topic.

Target campaigns are specified via GOOGLE_ADS_CAMPAIGN_IDS (comma-separated
numeric IDs). If the env var is not set, the action records success=False with
a clear message so the engine can continue to subsequent steps.

Uses the same GOOGLE_ADS_* credentials established in F5.

API reference:
  https://developers.google.com/google-ads/api/rest/reference/rest/v17/customers.campaignCriteria/mutate

In dry_run mode: returns the intended modifier payload without calling the API.
"""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

_API_BASE = "https://googleads.googleapis.com/v17"
_RETRY_DELAYS = (1.0, 2.0, 4.0)
_DEFAULT_BID_INCREASE_PCT = 15
_DEFAULT_MAX_CPC_LIMIT = 5.00


def execute(config: dict, golden_record: dict, dry_run: bool = False) -> dict:
    """Increase max CPC bid modifier for configured campaigns.

    Returns a result dict — never raises.
    """
    customer_id = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "").replace("-", "")
    developer_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    access_token = os.environ.get("GOOGLE_ADS_ACCESS_TOKEN", "")
    campaign_ids_raw = os.environ.get("GOOGLE_ADS_CAMPAIGN_IDS", "")

    bid_increase_pct = float(config.get("bid_increase_pct", _DEFAULT_BID_INCREASE_PCT))
    max_cpc_limit = float(config.get("max_cpc_limit", _DEFAULT_MAX_CPC_LIMIT))
    bid_modifier = round(1.0 + bid_increase_pct / 100.0, 4)

    topic = golden_record.get("topic_cluster", "unknown")

    if not campaign_ids_raw:
        return {
            "type": "bid_adjustment",
            "success": False,
            "dry_run": dry_run,
            "detail": "GOOGLE_ADS_CAMPAIGN_IDS is not configured — bid adjustment skipped",
            "error": "missing env var",
        }

    campaign_ids = [cid.strip() for cid in campaign_ids_raw.split(",") if cid.strip()]

    intended = {
        "topic_cluster": topic,
        "bid_modifier": bid_modifier,
        "bid_increase_pct": bid_increase_pct,
        "max_cpc_limit_micros": int(max_cpc_limit * 1_000_000),
        "campaign_count": len(campaign_ids),
    }

    if dry_run:
        return {
            "type": "bid_adjustment",
            "success": True,
            "dry_run": True,
            "detail": (
                f"DRY RUN — would apply {bid_increase_pct}% bid increase "
                f"(modifier={bid_modifier}) to {len(campaign_ids)} campaign(s)"
            ),
            "intended": intended,
        }

    if not customer_id or not developer_token or not access_token:
        return {
            "type": "bid_adjustment",
            "success": False,
            "dry_run": False,
            "detail": "Google Ads credentials not configured",
            "error": "missing GOOGLE_ADS_CUSTOMER_ID / DEVELOPER_TOKEN / ACCESS_TOKEN",
        }

    results: list[str] = []
    errors: list[str] = []

    for campaign_id in campaign_ids:
        try:
            resource_name = _apply_bid_modifier(
                customer_id=customer_id,
                campaign_id=campaign_id,
                bid_modifier=bid_modifier,
                max_cpc_micros=int(max_cpc_limit * 1_000_000),
                developer_token=developer_token,
                access_token=access_token,
            )
            results.append(resource_name)
            logger.info(
                "Bid adjustment applied: campaign=%s modifier=%.4f topic=%r",
                campaign_id,
                bid_modifier,
                topic,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Bid adjustment failed for campaign %s: %s", campaign_id, exc)
            errors.append(f"campaign {campaign_id}: {str(exc)[:100]}")

    if errors and not results:
        return {
            "type": "bid_adjustment",
            "success": False,
            "dry_run": False,
            "detail": f"All {len(campaign_ids)} bid adjustment(s) failed",
            "error": "; ".join(errors),
        }

    return {
        "type": "bid_adjustment",
        "success": True,
        "dry_run": False,
        "detail": (
            f"Bid modifier {bid_modifier} applied to {len(results)} campaign(s)"
            + (f" ({len(errors)} failed)" if errors else "")
        ),
    }


def _apply_bid_modifier(
    customer_id: str,
    campaign_id: str,
    bid_modifier: float,
    max_cpc_micros: int,
    developer_token: str,
    access_token: str,
) -> str:
    """POST a campaign criterion bid modifier to Google Ads. Returns resourceName."""
    url = f"{_API_BASE}/customers/{customer_id}/campaignBidModifiers:mutate"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": developer_token,
        "Content-Type": "application/json",
    }
    payload = {
        "operations": [
            {
                "create": {
                    "campaign": f"customers/{customer_id}/campaigns/{campaign_id}",
                    "bidModifier": bid_modifier,
                    "cpcBidCeilingMicros": str(max_cpc_micros),
                }
            }
        ]
    }

    last_exc: Exception | None = None
    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < len(_RETRY_DELAYS) - 1:
                time.sleep(delay)
                continue
            raise

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", delay))
            if attempt < len(_RETRY_DELAYS) - 1:
                time.sleep(retry_after)
                continue

        resp.raise_for_status()
        data = resp.json()
        return (data.get("results") or [{}])[0].get("resourceName", "")

    if last_exc:
        raise last_exc
    return ""
