"""Integration tests for F5 — Ad Platform Integration.

These tests require PostgreSQL (the audience_sync_log table from migration 006).
HTTP calls to Google Ads and Meta APIs are fully mocked — no network traffic.

Run with Docker services up:
    docker-compose up -d
    alembic upgrade head
    pytest tests/integration/test_ad_platforms.py -v
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from integrations._sync_log import already_synced, write_sync_log
from integrations.audience_mapper import AudienceSpec, load_mapping, map_audience
from integrations.google_ads import GoogleAdsAudienceSync
from integrations.meta_ads import MetaAudienceSync


# ── Shared fixtures ───────────────────────────────────────────────────────────

_AUDIENCE_PROXY = {
    "subreddits": ["r/MachineLearning", "r/artificial"],
    "handles": ["@OpenAI", "@AnthropicAI"],
    "top_topics": ["ai-chips", "GPU", "NVIDIA"],
    "site_sections": ["/ai", "/chips"],
}


@pytest.fixture(scope="module")
def golden_record_id(db_conn) -> str:
    """Insert a real golden record and clean up after the module."""
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=4)
    sql = """
        INSERT INTO golden_records
            (topic_cluster, mpi_score, signal_count, audience_proxy,
             recommended_action, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id::text
    """
    with db_conn.cursor() as cur:
        cur.execute(
            sql,
            (
                "ai-chips",
                0.88,
                25,
                json.dumps(_AUDIENCE_PROXY),
                "Activate paid acquisition for ai-chips.",
                expires_at,
            ),
        )
        record_id: str = cur.fetchone()[0]
    db_conn.commit()

    yield record_id

    with db_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM audience_sync_log WHERE golden_record_id = %s::uuid", (record_id,)
        )
        cur.execute("DELETE FROM golden_records WHERE id = %s::uuid", (record_id,))
    db_conn.commit()


@pytest.fixture()
def spec() -> AudienceSpec:
    mapping = load_mapping()
    return map_audience(_AUDIENCE_PROXY, "ai-chips", mapping)


# ── AudienceMapper ────────────────────────────────────────────────────────────


class TestAudienceMapper:
    def test_map_audience_includes_mapping_keywords(self, spec):
        assert "AI chips" in spec.keywords or "ai-chips" in spec.keywords

    def test_map_audience_includes_proxy_topics(self, spec):
        assert "GPU" in spec.keywords
        assert "NVIDIA" in spec.keywords

    def test_map_audience_deduplicates_keywords(self, spec):
        assert len(spec.keywords) == len(set(spec.keywords))

    def test_map_audience_preserves_subreddits_and_handles(self, spec):
        assert "r/MachineLearning" in spec.subreddits
        assert "@OpenAI" in spec.handles

    def test_map_audience_falls_back_to_default_for_unknown_cluster(self):
        mapping = load_mapping()
        spec = map_audience({"top_topics": ["unknown-thing"]}, "unknown-cluster-xyz", mapping)
        assert isinstance(spec.keywords, list)
        assert len(spec.keywords) >= 1  # at least the proxy topic

    def test_map_audience_keywords_capped_at_50(self):
        many_topics = [f"topic-{i}" for i in range(100)]
        spec = map_audience({"top_topics": many_topics}, "ai-chips", {})
        assert len(spec.keywords) <= 50

    def test_map_audience_interests_capped_at_25(self):
        many_topics = [f"topic-{i}" for i in range(100)]
        spec = map_audience({"top_topics": many_topics}, "ai-chips", {})
        assert len(spec.interests) <= 25


# ── SyncLog helpers ───────────────────────────────────────────────────────────


class TestSyncLog:
    def test_write_and_read_success(self, db_conn, golden_record_id):
        write_sync_log(
            db_conn,
            golden_record_id,
            "google_ads",
            "success",
            audience_id="customers/123/userLists/456",
        )
        db_conn.commit()
        assert already_synced(db_conn, golden_record_id, "google_ads") is True

    def test_already_synced_returns_false_for_unseen_record(self, db_conn):
        fake_id = str(uuid.uuid4())
        assert already_synced(db_conn, fake_id, "meta") is False

    def test_already_synced_false_for_error_status(self, db_conn, golden_record_id):
        # Write an error row for meta; already_synced should still be False
        write_sync_log(
            db_conn,
            golden_record_id,
            "meta",
            "error",
            error_message="Connection timeout",
        )
        db_conn.commit()
        assert already_synced(db_conn, golden_record_id, "meta") is False

    def test_upsert_updates_existing_row(self, db_conn, golden_record_id):
        # Write error first, then overwrite with success
        write_sync_log(db_conn, golden_record_id, "meta", "error", error_message="first")
        db_conn.commit()
        write_sync_log(db_conn, golden_record_id, "meta", "success", audience_id="act_789/audiences/111")
        db_conn.commit()
        assert already_synced(db_conn, golden_record_id, "meta") is True

    def test_error_message_is_truncated_at_500_chars(self, db_conn):
        fake_id = str(uuid.uuid4())
        # Insert golden record first
        sql = """
            INSERT INTO golden_records (topic_cluster, mpi_score, signal_count, recommended_action, expires_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id::text
        """
        with db_conn.cursor() as cur:
            cur.execute(sql, ("test", 0.8, 1, "test", datetime.now(tz=timezone.utc) + timedelta(hours=1)))
            rec_id = cur.fetchone()[0]
        db_conn.commit()

        long_error = "E" * 1000
        write_sync_log(db_conn, rec_id, "google_ads", "error", error_message=long_error)
        db_conn.commit()

        with db_conn.cursor() as cur:
            cur.execute("SELECT error_message FROM audience_sync_log WHERE golden_record_id = %s::uuid", (rec_id,))
            stored = cur.fetchone()[0]
        assert stored is not None
        assert len(stored) <= 500

        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM audience_sync_log WHERE golden_record_id = %s::uuid", (rec_id,))
            cur.execute("DELETE FROM golden_records WHERE id = %s::uuid", (rec_id,))
        db_conn.commit()


# ── GoogleAdsAudienceSync ─────────────────────────────────────────────────────


def _google_ads_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_CUSTOMER_ID", "1234567890")
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "test-dev-token")
    monkeypatch.setenv("GOOGLE_ADS_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setenv("GOOGLE_ADS_ENABLED", "true")


class TestGoogleAdsAudienceSync:
    def test_sync_returns_resource_name(self, monkeypatch, golden_record_id, spec):
        _google_ads_env(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{"resourceName": "customers/123/userLists/789"}]
        }

        with patch("integrations.google_ads.requests.post", return_value=mock_resp) as mock_post:
            syncer = GoogleAdsAudienceSync()
            result = syncer.sync(golden_record_id, spec)

        assert result == "customers/123/userLists/789"
        mock_post.assert_called_once()

    def test_sync_payload_contains_topic_keywords(self, monkeypatch, golden_record_id, spec):
        _google_ads_env(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"resourceName": "customers/123/userLists/1"}]}

        with patch("integrations.google_ads.requests.post", return_value=mock_resp) as mock_post:
            GoogleAdsAudienceSync().sync(golden_record_id, spec)

        call_kwargs = mock_post.call_args
        sent_payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        operations = sent_payload["operations"]
        assert len(operations) == 1
        create_op = operations[0]["create"]
        assert "trend-arb-" in create_op["name"]
        rule_items = (
            create_op["ruleBasedUserList"]["flexibleRuleUserList"]["inclusiveOperands"]
        )
        keyword_values = [
            item["rule"]["ruleItemGroups"][0]["ruleItems"][0]["urlRuleItem"]["value"]
            for item in rule_items
        ]
        assert len(keyword_values) >= 1

    def test_sync_retries_on_429_then_succeeds(self, monkeypatch, golden_record_id, spec):
        _google_ads_env(monkeypatch)
        throttled = MagicMock(status_code=429, headers={"Retry-After": "0"})
        throttled.raise_for_status.side_effect = requests.HTTPError(response=throttled)
        success = MagicMock(status_code=200)
        success.json.return_value = {"results": [{"resourceName": "customers/123/userLists/2"}]}

        side_effects = [throttled, success]

        with patch("integrations.google_ads.requests.post", side_effect=side_effects):
            with patch("integrations.google_ads.time.sleep"):
                result = GoogleAdsAudienceSync().sync(golden_record_id, spec)

        assert result == "customers/123/userLists/2"

    def test_sync_raises_on_persistent_429(self, monkeypatch, golden_record_id, spec):
        _google_ads_env(monkeypatch)
        throttled = MagicMock(status_code=429, headers={"Retry-After": "0"})
        throttled.raise_for_status.side_effect = requests.HTTPError(response=throttled)

        with patch("integrations.google_ads.requests.post", return_value=throttled):
            with patch("integrations.google_ads.time.sleep"):
                with pytest.raises(requests.HTTPError):
                    GoogleAdsAudienceSync().sync(golden_record_id, spec)

    def test_sync_returns_none_when_disabled(self, monkeypatch, golden_record_id, spec):
        monkeypatch.setenv("GOOGLE_ADS_ENABLED", "false")
        result = GoogleAdsAudienceSync().sync(golden_record_id, spec)
        assert result is None

    def test_sync_raises_runtime_error_when_not_configured(self, monkeypatch, golden_record_id, spec):
        monkeypatch.setenv("GOOGLE_ADS_ENABLED", "true")
        monkeypatch.setenv("GOOGLE_ADS_CUSTOMER_ID", "")
        monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
        monkeypatch.setenv("GOOGLE_ADS_ACCESS_TOKEN", "")
        with pytest.raises(RuntimeError, match="GOOGLE_ADS"):
            GoogleAdsAudienceSync().sync(golden_record_id, spec)

    def test_sync_logs_success_to_sync_log(self, monkeypatch, db_conn, spec):
        _google_ads_env(monkeypatch)
        # Fresh golden record for this test
        sql = """
            INSERT INTO golden_records (topic_cluster, mpi_score, signal_count, recommended_action, expires_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id::text
        """
        with db_conn.cursor() as cur:
            cur.execute(sql, ("ai-chips", 0.9, 5, "test", datetime.now(tz=timezone.utc) + timedelta(hours=1)))
            rec_id = cur.fetchone()[0]
        db_conn.commit()

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"results": [{"resourceName": "customers/123/userLists/99"}]}

        with patch("integrations.google_ads.requests.post", return_value=mock_resp):
            audience_id = GoogleAdsAudienceSync().sync(rec_id, spec)

        write_sync_log(db_conn, rec_id, "google_ads", "success", audience_id=audience_id)
        db_conn.commit()

        assert already_synced(db_conn, rec_id, "google_ads") is True

        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM audience_sync_log WHERE golden_record_id = %s::uuid", (rec_id,))
            cur.execute("DELETE FROM golden_records WHERE id = %s::uuid", (rec_id,))
        db_conn.commit()


# ── MetaAudienceSync ──────────────────────────────────────────────────────────


def _meta_env(monkeypatch):
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "act_123456789")
    monkeypatch.setenv("META_ACCESS_TOKEN", "test-meta-token")
    monkeypatch.setenv("META_ADS_ENABLED", "true")


class TestMetaAudienceSync:
    def test_sync_returns_audience_id(self, monkeypatch, golden_record_id, spec):
        _meta_env(monkeypatch)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"id": "23849012345678"}

        with patch("integrations.meta_ads.requests.post", return_value=mock_resp) as mock_post:
            result = MetaAudienceSync().sync(golden_record_id, spec)

        assert result == "23849012345678"
        mock_post.assert_called_once()

    def test_sync_payload_has_correct_structure(self, monkeypatch, golden_record_id, spec):
        _meta_env(monkeypatch)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"id": "999"}

        with patch("integrations.meta_ads.requests.post", return_value=mock_resp) as mock_post:
            MetaAudienceSync().sync(golden_record_id, spec)

        sent_data = mock_post.call_args.kwargs.get("data") or mock_post.call_args.args[1]
        assert sent_data["subtype"] == "CUSTOM"
        assert "trend-arb-" in sent_data["name"]
        assert len(sent_data["description"]) <= 100

    def test_sync_normalises_account_id_without_act_prefix(self, monkeypatch, golden_record_id, spec):
        monkeypatch.setenv("META_AD_ACCOUNT_ID", "123456789")  # no act_ prefix
        monkeypatch.setenv("META_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("META_ADS_ENABLED", "true")

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"id": "111"}

        with patch("integrations.meta_ads.requests.post", return_value=mock_resp) as mock_post:
            MetaAudienceSync().sync(golden_record_id, spec)

        called_url: str = mock_post.call_args.args[0]
        assert "act_123456789" in called_url

    def test_sync_retries_on_429_then_succeeds(self, monkeypatch, golden_record_id, spec):
        _meta_env(monkeypatch)
        throttled = MagicMock(status_code=429, headers={"Retry-After": "0"})
        throttled.raise_for_status.side_effect = requests.HTTPError(response=throttled)
        success = MagicMock(status_code=200)
        success.json.return_value = {"id": "777"}

        with patch("integrations.meta_ads.requests.post", side_effect=[throttled, success]):
            with patch("integrations.meta_ads.time.sleep"):
                result = MetaAudienceSync().sync(golden_record_id, spec)

        assert result == "777"

    def test_sync_raises_on_persistent_429(self, monkeypatch, golden_record_id, spec):
        _meta_env(monkeypatch)
        throttled = MagicMock(status_code=429, headers={"Retry-After": "0"})
        throttled.raise_for_status.side_effect = requests.HTTPError(response=throttled)

        with patch("integrations.meta_ads.requests.post", return_value=throttled):
            with patch("integrations.meta_ads.time.sleep"):
                with pytest.raises(requests.HTTPError):
                    MetaAudienceSync().sync(golden_record_id, spec)

    def test_sync_returns_none_when_disabled(self, monkeypatch, golden_record_id, spec):
        monkeypatch.setenv("META_ADS_ENABLED", "false")
        result = MetaAudienceSync().sync(golden_record_id, spec)
        assert result is None

    def test_sync_raises_runtime_error_when_not_configured(self, monkeypatch, golden_record_id, spec):
        monkeypatch.setenv("META_ADS_ENABLED", "true")
        monkeypatch.setenv("META_AD_ACCOUNT_ID", "")
        monkeypatch.setenv("META_ACCESS_TOKEN", "")
        with pytest.raises(RuntimeError, match="META_"):
            MetaAudienceSync().sync(golden_record_id, spec)

    def test_sync_error_is_logged_to_sync_log(self, monkeypatch, db_conn, spec):
        _meta_env(monkeypatch)
        sql = """
            INSERT INTO golden_records (topic_cluster, mpi_score, signal_count, recommended_action, expires_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id::text
        """
        with db_conn.cursor() as cur:
            cur.execute(sql, ("ai-chips", 0.85, 3, "test", datetime.now(tz=timezone.utc) + timedelta(hours=1)))
            rec_id = cur.fetchone()[0]
        db_conn.commit()

        error_resp = MagicMock(status_code=400)
        error_resp.raise_for_status.side_effect = requests.HTTPError("400 Bad Request")

        with patch("integrations.meta_ads.requests.post", return_value=error_resp):
            with pytest.raises(requests.HTTPError):
                MetaAudienceSync().sync(rec_id, spec)

        write_sync_log(db_conn, rec_id, "meta", "error", error_message="400 Bad Request")
        db_conn.commit()

        assert already_synced(db_conn, rec_id, "meta") is False

        with db_conn.cursor() as cur:
            cur.execute("SELECT status FROM audience_sync_log WHERE golden_record_id = %s::uuid AND platform = 'meta'", (rec_id,))
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "error"

        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM audience_sync_log WHERE golden_record_id = %s::uuid", (rec_id,))
            cur.execute("DELETE FROM golden_records WHERE id = %s::uuid", (rec_id,))
        db_conn.commit()
