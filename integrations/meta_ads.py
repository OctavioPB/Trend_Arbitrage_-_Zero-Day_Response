"""Meta Ads audience sync — creates a Custom Audience from topic interests and handles.

Uses the Meta Marketing API to create a CUSTOM audience shell. Marketing teams
attach interest targeting and lookalike sources to the audience in Ads Manager.

API reference:
  https://developers.facebook.com/docs/marketing-api/reference/custom-audience/

Retry policy: up to 3 attempts with exponential back-off on HTTP 429.
Platform errors (4xx except 429, 5xx) are raised immediately so the DAG task
can log them to audience_sync_log without retrying invalid payloads.
"""

from __future__ import annotations

import logging
import os
import time

import requests

from integrations.audience_mapper import AudienceSpec

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v18.0"
_RETRY_DELAYS = (1.0, 2.0, 4.0)
_MAX_DESCRIPTION_LEN = 100   # Meta API limit


class MetaAudienceSync:
    """Create a Meta Custom Audience for the given Golden Record."""

    def __init__(self) -> None:
        self._ad_account_id = os.environ.get("META_AD_ACCOUNT_ID", "")
        self._access_token = os.environ.get("META_ACCESS_TOKEN", "")
        self._enabled = os.environ.get("META_ADS_ENABLED", "true").lower() == "true"

    # ── Public API ─────────────────────────────────────────────────────────────

    def sync(self, golden_record_id: str, spec: AudienceSpec) -> str | None:
        """Create a Meta Custom Audience for the given AudienceSpec.

        Returns:
            audience_id (string) on success.
            None if the integration is disabled via META_ADS_ENABLED=false.

        Raises:
            RuntimeError: missing configuration.
            requests.HTTPError: non-retryable API error.
        """
        if not self._enabled:
            logger.info(
                "Meta Ads sync disabled — skipping golden_record_id=%s", golden_record_id
            )
            return None

        self._assert_configured()

        # Normalise account ID — API expects act_{id}
        account_id = self._ad_account_id
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"

        payload = self._build_payload(golden_record_id, spec)
        url = f"{_GRAPH_BASE}/{account_id}/customaudiences"
        data = self._post_with_retry(url, payload)

        audience_id: str = str(data.get("id", ""))
        logger.info(
            "Meta Custom Audience created: golden_record_id=%s audience_id=%s",
            golden_record_id,
            audience_id,
        )
        return audience_id

    # ── Private helpers ────────────────────────────────────────────────────────

    def _assert_configured(self) -> None:
        missing = [
            name
            for name, val in (
                ("META_AD_ACCOUNT_ID", self._ad_account_id),
                ("META_ACCESS_TOKEN", self._access_token),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Meta Ads sync requires env vars: {', '.join(missing)}"
            )

    def _build_payload(self, golden_record_id: str, spec: AudienceSpec) -> dict:
        name = f"trend-arb-{spec.topic_cluster[:40]}-{golden_record_id[:8]}"

        # Build a concise description from interests + handles
        parts: list[str] = []
        if spec.interests:
            parts.append(", ".join(spec.interests[:5]))
        if spec.handles:
            parts.append("handles: " + ", ".join(spec.handles[:3]))
        description = "; ".join(parts)[:_MAX_DESCRIPTION_LEN]

        return {
            "name": name,
            "subtype": "CUSTOM",
            "description": description or f"Trend Arbitrage — {spec.topic_cluster}",
            "customer_file_source": "PARTNER_PROVIDED_ONLY",
            "access_token": self._access_token,
        }

    def _post_with_retry(self, url: str, payload: dict) -> dict:
        last_exc: Exception | None = None
        for attempt, delay in enumerate(_RETRY_DELAYS):
            try:
                resp = requests.post(url, data=payload, timeout=15)
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
            return resp.json()

        if last_exc:
            raise last_exc
        return {}
