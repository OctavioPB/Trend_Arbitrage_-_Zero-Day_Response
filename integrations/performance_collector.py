"""Collect ad-platform performance metrics for Golden Record audiences.

For each Golden Record whose audience was successfully synced to an ad platform
(audience_sync_log.status = 'success'), this module queries the platform for
campaign metrics in the measurement window (default: 24 hours after sync) and
writes the results to performance_events.

Collection is idempotent: the UNIQUE constraint on performance_events
(golden_record_id, platform, metric, measurement_window_hours) prevents duplicates.

Google Ads:
    Queries campaign metrics (CTR, conversions, search_impression_share) for all
    campaign IDs in GOOGLE_ADS_CAMPAIGN_IDS over [synced_at, synced_at + window_h].
    The per-campaign average is attributed to the golden_record_id.

Meta:
    Queries account-level ad insights (CTR, conversions/actions) for the same
    window using the account insights endpoint.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

_API_BASE_GOOGLE = "https://googleads.googleapis.com/v17"
_GRAPH_BASE_META = "https://graph.facebook.com/v18.0"
_RETRY_DELAYS = (1.0, 2.0, 4.0)

_GOOGLE_ENABLED = os.environ.get("GOOGLE_ADS_ENABLED", "true").lower() == "true"
_META_ENABLED = os.environ.get("META_ADS_ENABLED", "true").lower() == "true"


class PerformanceCollector:
    """Collect campaign performance metrics from Google Ads and Meta."""

    def __init__(self) -> None:
        # Google Ads credentials
        self._gads_customer_id = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "").replace("-", "")
        self._gads_developer_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
        self._gads_access_token = os.environ.get("GOOGLE_ADS_ACCESS_TOKEN", "")
        self._gads_campaign_ids: list[str] = [
            cid.strip()
            for cid in os.environ.get("GOOGLE_ADS_CAMPAIGN_IDS", "").split(",")
            if cid.strip()
        ]

        # Meta credentials
        self._meta_ad_account_id = os.environ.get("META_AD_ACCOUNT_ID", "")
        self._meta_access_token = os.environ.get("META_ACCESS_TOKEN", "")

    # ── Public API ─────────────────────────────────────────────────────────────

    def collect(self, conn, window_hours: int = 24) -> int:
        """Collect performance metrics for all eligible audience syncs.

        Eligible = synced_at older than window_hours (measurement period elapsed)
        and not yet collected for this (golden_record_id, platform, metric, window).

        Returns:
            Number of new performance_events rows written.
        """
        rows = self._load_eligible_syncs(conn, window_hours)
        written = 0

        for row in rows:
            golden_record_id = row["golden_record_id"]
            platform = row["platform"]
            synced_at: datetime = row["synced_at"]

            try:
                if platform == "google_ads" and _GOOGLE_ENABLED:
                    events = self._collect_google(golden_record_id, synced_at, window_hours)
                elif platform == "meta" and _META_ENABLED:
                    events = self._collect_meta(golden_record_id, synced_at, window_hours)
                else:
                    logger.debug(
                        "Platform %s disabled or unknown — skipping golden_record_id=%s",
                        platform,
                        golden_record_id,
                    )
                    continue

                for metric, value in events.items():
                    if not self._already_collected(
                        conn, golden_record_id, platform, metric, window_hours
                    ):
                        self._write_event(
                            conn, golden_record_id, platform, metric, value, window_hours
                        )
                        written += 1

                conn.commit()

            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                logger.error(
                    "Performance collection failed: golden_record_id=%s platform=%s: %s",
                    golden_record_id,
                    platform,
                    exc,
                )

        logger.info("performance_collector: wrote %d new event(s)", written)
        return written

    # ── DB helpers ─────────────────────────────────────────────────────────────

    def _load_eligible_syncs(self, conn, window_hours: int) -> list[dict]:
        """Return audience_sync_log rows eligible for performance collection.

        Eligible = status='success' AND synced_at <= NOW() - window_hours
        (measurement window has elapsed) AND no performance_events row yet exists
        for this (golden_record_id, platform) combination.
        """
        sql = """
            SELECT asl.golden_record_id::text,
                   asl.platform,
                   asl.audience_id,
                   asl.synced_at
            FROM audience_sync_log asl
            WHERE asl.status = 'success'
              AND asl.synced_at <= NOW() - (%s * INTERVAL '1 hour')
              AND NOT EXISTS (
                  SELECT 1 FROM performance_events pe
                  WHERE pe.golden_record_id = asl.golden_record_id
                    AND pe.platform = asl.platform
                    AND pe.measurement_window_hours = %s
              )
        """
        with conn.cursor() as cur:
            cur.execute(sql, (window_hours, window_hours))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _already_collected(
        self,
        conn,
        golden_record_id: str,
        platform: str,
        metric: str,
        window_hours: int,
    ) -> bool:
        sql = """
            SELECT 1 FROM performance_events
            WHERE golden_record_id = %s::uuid
              AND platform = %s
              AND metric = %s
              AND measurement_window_hours = %s
            LIMIT 1
        """
        with conn.cursor() as cur:
            cur.execute(sql, (golden_record_id, platform, metric, window_hours))
            return cur.fetchone() is not None

    def _write_event(
        self,
        conn,
        golden_record_id: str,
        platform: str,
        metric: str,
        value: float,
        window_hours: int,
    ) -> None:
        sql = """
            INSERT INTO performance_events
                (golden_record_id, platform, metric, value, measurement_window_hours)
            VALUES (%s::uuid, %s, %s, %s, %s)
            ON CONFLICT (golden_record_id, platform, metric, measurement_window_hours)
            DO NOTHING
        """
        with conn.cursor() as cur:
            cur.execute(sql, (golden_record_id, platform, metric, value, window_hours))
        logger.debug(
            "performance_event written: gr=%s platform=%s metric=%s value=%.4f",
            golden_record_id,
            platform,
            metric,
            value,
        )

    # ── Google Ads ─────────────────────────────────────────────────────────────

    def _collect_google(
        self,
        golden_record_id: str,
        synced_at: datetime,
        window_hours: int,
    ) -> dict[str, float]:
        """Query campaign metrics from Google Ads for the measurement window.

        Returns a dict of {metric_name: value} averaged across all campaign IDs.
        Returns empty dict if credentials are missing or no campaign IDs configured.
        """
        if not all([self._gads_customer_id, self._gads_developer_token, self._gads_access_token]):
            logger.warning(
                "Google Ads credentials incomplete — skipping golden_record_id=%s",
                golden_record_id,
            )
            return {}

        if not self._gads_campaign_ids:
            logger.warning(
                "GOOGLE_ADS_CAMPAIGN_IDS not set — skipping golden_record_id=%s",
                golden_record_id,
            )
            return {}

        start_date = synced_at.strftime("%Y-%m-%d")
        end_dt = synced_at + timedelta(hours=window_hours)
        end_date = end_dt.strftime("%Y-%m-%d")

        ids_clause = ", ".join(self._gads_campaign_ids)
        query = (
            "SELECT campaign.id, metrics.ctr, metrics.conversions, "
            "metrics.search_impression_share "
            f"FROM campaign "
            f"WHERE campaign.id IN ({ids_clause}) "
            f"AND segments.date BETWEEN '{start_date}' AND '{end_date}'"
        )

        url = f"{_API_BASE_GOOGLE}/customers/{self._gads_customer_id}/googleAds:search"
        headers = {
            "Authorization": f"Bearer {self._gads_access_token}",
            "developer-token": self._gads_developer_token,
            "Content-Type": "application/json",
        }

        data = self._post_with_retry(url, {"query": query}, headers)
        results = data.get("results") or []

        if not results:
            return {}

        total_ctr = sum(r.get("metrics", {}).get("ctr", 0.0) for r in results)
        total_conv = sum(r.get("metrics", {}).get("conversions", 0.0) for r in results)
        total_imp_share = sum(
            r.get("metrics", {}).get("searchImpressionShare", 0.0) for r in results
        )
        n = len(results)

        return {
            "ctr": total_ctr / n,
            "conversions": total_conv,
            "impression_share": total_imp_share / n,
        }

    # ── Meta ───────────────────────────────────────────────────────────────────

    def _collect_meta(
        self,
        golden_record_id: str,
        synced_at: datetime,
        window_hours: int,
    ) -> dict[str, float]:
        """Query ad account insights from Meta for the measurement window.

        Returns a dict of {metric_name: value} for the account during the window.
        Returns empty dict if credentials are missing.
        """
        if not all([self._meta_ad_account_id, self._meta_access_token]):
            logger.warning(
                "Meta credentials incomplete — skipping golden_record_id=%s",
                golden_record_id,
            )
            return {}

        account_id = self._meta_ad_account_id
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"

        start_dt = synced_at
        end_dt = synced_at + timedelta(hours=window_hours)
        time_range = {
            "since": start_dt.strftime("%Y-%m-%d"),
            "until": end_dt.strftime("%Y-%m-%d"),
        }

        url = f"{_GRAPH_BASE_META}/{account_id}/insights"
        params = {
            "fields": "ctr,actions,impressions",
            "time_range": str(time_range).replace("'", '"'),
            "level": "account",
            "access_token": self._meta_access_token,
        }

        resp = self._get_with_retry(url, params)
        entries = (resp.get("data") or [])

        if not entries:
            return {}

        entry = entries[0]
        ctr = float(entry.get("ctr", 0.0))
        impressions = float(entry.get("impressions", 0.0))

        # Extract purchase/lead conversions from actions list
        actions: list[dict] = entry.get("actions") or []
        conversions = sum(
            float(a.get("value", 0.0))
            for a in actions
            if a.get("action_type") in ("purchase", "lead", "complete_registration")
        )

        return {
            "ctr": ctr,
            "conversions": conversions,
            "impression_share": min(impressions / 1_000_000, 1.0) if impressions else 0.0,
        }

    # ── HTTP helpers ───────────────────────────────────────────────────────────

    def _post_with_retry(self, url: str, payload: dict, headers: dict) -> dict:
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
            return resp.json()

        if last_exc:
            raise last_exc
        return {}

    def _get_with_retry(self, url: str, params: dict) -> dict:
        last_exc: Exception | None = None
        for attempt, delay in enumerate(_RETRY_DELAYS):
            try:
                resp = requests.get(url, params=params, timeout=15)
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
