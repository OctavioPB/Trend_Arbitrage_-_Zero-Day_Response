"""Unit tests for alerting.notifier and alerting.config.

All external I/O (DB, HTTP, SMTP) is mocked. These tests never hit the network.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from alerting.config import AlertRule, _row_to_rule
from alerting.notifier import (
    AlertBackend,
    AlertNotifier,
    AlertPayload,
    EmailBackend,
    SlackBackend,
    WebhookBackend,
    build_backend,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
_EXPIRES = _NOW + timedelta(hours=4)


def _make_payload(**overrides) -> AlertPayload:
    base = dict(
        topic="ai-chips",
        mpi_score=0.85,
        signal_count=42,
        recommended_action="Activate paid acquisition",
        expires_at=_EXPIRES,
        dashboard_url="http://localhost:5173",
    )
    base.update(overrides)
    return AlertPayload(**base)


def _make_rule(**overrides) -> AlertRule:
    base = dict(
        id="rule-001",
        topic_cluster="*",
        min_mpi=0.72,
        min_signal_count=1,
        suppression_minutes=30,
        channels=[{"type": "slack", "webhook_url": "https://hooks.slack.com/test"}],
        enabled=True,
        last_alerted_at=None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    base.update(overrides)
    return AlertRule(**base)


def _make_golden_record(**overrides) -> dict:
    base = dict(
        id="gr-001",
        topic_cluster="ai-chips",
        mpi_score=0.85,
        signal_count=42,
        recommended_action="Activate paid acquisition",
        expires_at=_EXPIRES.isoformat(),
        audience_proxy={},
    )
    base.update(overrides)
    return base


# ── AlertPayload ──────────────────────────────────────────────────────────────


class TestAlertPayload:
    def test_from_golden_record_parses_iso_expires(self):
        record = _make_golden_record()
        payload = AlertPayload.from_golden_record(record)
        assert payload.topic == "ai-chips"
        assert payload.mpi_score == pytest.approx(0.85)
        assert payload.signal_count == 42
        assert payload.expires_at == _EXPIRES

    def test_from_golden_record_parses_datetime_expires(self):
        record = _make_golden_record(expires_at=_EXPIRES)
        payload = AlertPayload.from_golden_record(record)
        assert payload.expires_at == _EXPIRES

    def test_model_dump_safe_redacts_password(self):
        payload = _make_payload(dashboard_url="postgresql://user:secret@localhost/db")
        safe = payload.model_dump_safe()
        assert safe["dashboard_url"] == "[REDACTED]"

    def test_model_dump_safe_redacts_api_key(self):
        payload = _make_payload(recommended_action="use sk-ant-xxxx token")
        safe = payload.model_dump_safe()
        assert safe["recommended_action"] == "[REDACTED]"

    def test_model_dump_safe_leaves_safe_fields_intact(self):
        payload = _make_payload()
        safe = payload.model_dump_safe()
        assert safe["topic"] == "ai-chips"
        assert safe["mpi_score"] == pytest.approx(0.85)
        assert safe["signal_count"] == 42


# ── SlackBackend ──────────────────────────────────────────────────────────────


class TestSlackBackend:
    def test_name(self):
        assert SlackBackend("https://hooks.slack.com/test").name == "slack"

    @patch("alerting.notifier.requests.post")
    def test_send_posts_to_webhook(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        backend = SlackBackend("https://hooks.slack.com/test")
        backend.send(_make_payload())
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://hooks.slack.com/test"
        assert "blocks" in kwargs["json"]

    @patch("alerting.notifier.requests.post")
    def test_block_kit_contains_topic(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        backend = SlackBackend("https://hooks.slack.com/test")
        backend.send(_make_payload())
        body = mock_post.call_args.kwargs["json"]
        blocks_text = json.dumps(body["blocks"])
        assert "ai-chips" in blocks_text

    @patch("alerting.notifier.requests.post")
    def test_send_includes_dashboard_button_when_url_set(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        backend = SlackBackend("https://hooks.slack.com/test")
        backend.send(_make_payload(dashboard_url="http://localhost:5173"))
        body = mock_post.call_args.kwargs["json"]
        block_types = [b["type"] for b in body["blocks"]]
        assert "actions" in block_types

    @patch("alerting.notifier.requests.post")
    def test_send_omits_dashboard_button_when_no_url(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        backend = SlackBackend("https://hooks.slack.com/test")
        backend.send(_make_payload(dashboard_url=""))
        body = mock_post.call_args.kwargs["json"]
        block_types = [b["type"] for b in body["blocks"]]
        assert "actions" not in block_types

    @patch("alerting.notifier.requests.post")
    def test_send_raises_on_http_error(self, mock_post):
        import requests

        mock_post.return_value.raise_for_status = MagicMock(
            side_effect=requests.HTTPError("500")
        )
        backend = SlackBackend("https://hooks.slack.com/test")
        with pytest.raises(requests.HTTPError):
            backend.send(_make_payload())


# ── WebhookBackend ────────────────────────────────────────────────────────────


class TestWebhookBackend:
    def test_name(self):
        assert WebhookBackend("https://example.com/hook").name == "webhook"

    @patch("alerting.notifier.requests.post")
    def test_send_posts_safe_payload(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        backend = WebhookBackend("https://example.com/hook", headers={"X-Token": "abc"})
        backend.send(_make_payload())
        call_kwargs = mock_post.call_args.kwargs
        # Headers merged: Content-Type + custom
        assert call_kwargs["headers"]["X-Token"] == "abc"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"
        # Payload uses model_dump_safe — no credentials
        body = call_kwargs["json"]
        assert body["topic"] == "ai-chips"

    @patch("alerting.notifier.requests.post")
    def test_send_no_custom_headers(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        backend = WebhookBackend("https://example.com/hook")
        backend.send(_make_payload())
        headers = mock_post.call_args.kwargs["headers"]
        assert headers == {"Content-Type": "application/json"}


# ── EmailBackend ──────────────────────────────────────────────────────────────


class TestEmailBackend:
    def _make_backend(self) -> EmailBackend:
        return EmailBackend(
            host="smtp.gmail.com",
            port=587,
            user="sender@gmail.com",
            password="secret",
            from_addr="sender@gmail.com",
            to_addrs=["recv@example.com"],
        )

    def test_name(self):
        assert self._make_backend().name == "email"

    @patch("alerting.notifier.smtplib.SMTP")
    def test_send_calls_starttls_and_login(self, mock_smtp_cls):
        smtp_instance = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        self._make_backend().send(_make_payload())

        smtp_instance.ehlo.assert_called_once()
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("sender@gmail.com", "secret")

    @patch("alerting.notifier.smtplib.SMTP")
    def test_send_subject_contains_topic_and_mpi(self, mock_smtp_cls):
        smtp_instance = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        self._make_backend().send(_make_payload())

        sendmail_call = smtp_instance.sendmail.call_args
        raw_msg = sendmail_call[0][2]
        assert "ai-chips" in raw_msg
        assert "0.850" in raw_msg


# ── build_backend factory ─────────────────────────────────────────────────────


class TestBuildBackend:
    def test_builds_slack(self):
        b = build_backend({"type": "slack", "webhook_url": "https://hooks.slack.com/x"})
        assert isinstance(b, SlackBackend)

    def test_builds_webhook(self):
        b = build_backend({"type": "webhook", "url": "https://example.com/hook"})
        assert isinstance(b, WebhookBackend)

    def test_builds_email(self):
        b = build_backend({
            "type": "email",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "u",
            "smtp_password": "p",
            "from_addr": "f@g.com",
            "to_addrs": ["t@g.com"],
        })
        assert isinstance(b, EmailBackend)

    def test_returns_none_for_unknown_type(self):
        b = build_backend({"type": "pagerduty"})
        assert b is None

    def test_returns_none_for_missing_required_key(self):
        # Slack without webhook_url
        b = build_backend({"type": "slack"})
        assert b is None

    def test_returns_none_for_email_missing_key(self):
        b = build_backend({"type": "email", "smtp_host": "h"})
        assert b is None


# ── AlertNotifier.fire — integration-level unit tests ─────────────────────────


class TestAlertNotifierFire:
    """All DB calls patched out; tests focus on routing logic."""

    def _notifier(self) -> AlertNotifier:
        return AlertNotifier(dashboard_url="http://localhost:5173", dsn="postgresql://test")

    def _rule_with_slack(self) -> AlertRule:
        return _make_rule(
            channels=[{"type": "slack", "webhook_url": "https://hooks.slack.com/r1"}]
        )

    def _rule_cluster_specific(self) -> AlertRule:
        return _make_rule(
            id="rule-002",
            topic_cluster="ai-chips",  # exact match only
            channels=[{"type": "slack", "webhook_url": "https://hooks.slack.com/r2"}],
        )

    @patch("alerting.notifier.psycopg2.connect")
    @patch("alerting.config.psycopg2.extras.RealDictCursor")
    def test_fire_calls_backend_send(self, _mock_cursor, mock_connect):
        rule = self._rule_with_slack()

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        from alerting import config as cfg

        with patch.object(cfg, "get_matching_rules", return_value=[rule]):
            with patch.object(cfg, "update_last_alerted") as mock_stamp:
                with patch("alerting.notifier.SlackBackend.send") as mock_send:
                    self._notifier().fire(_make_golden_record())

        mock_send.assert_called_once()

    @patch("alerting.notifier.psycopg2.connect")
    def test_fire_stamps_suppression_clock_after_success(self, mock_connect):
        rule = self._rule_with_slack()

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        from alerting import config as cfg

        with patch.object(cfg, "get_matching_rules", return_value=[rule]):
            with patch.object(cfg, "update_last_alerted") as mock_stamp:
                with patch("alerting.notifier.SlackBackend.send"):
                    self._notifier().fire(_make_golden_record())

        mock_stamp.assert_called_once_with(mock_conn, rule.id)

    @patch("alerting.notifier.psycopg2.connect")
    def test_fire_does_not_stamp_if_all_backends_fail(self, mock_connect):
        rule = self._rule_with_slack()

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        from alerting import config as cfg

        with patch.object(cfg, "get_matching_rules", return_value=[rule]):
            with patch.object(cfg, "update_last_alerted") as mock_stamp:
                with patch(
                    "alerting.notifier.SlackBackend.send",
                    side_effect=RuntimeError("network error"),
                ):
                    self._notifier().fire(_make_golden_record())

        mock_stamp.assert_not_called()

    @patch("alerting.notifier.psycopg2.connect")
    def test_fire_continues_other_backends_after_one_fails(self, mock_connect):
        """If backend 1 fails, backend 2 must still be called."""
        rule = _make_rule(
            channels=[
                {"type": "slack", "webhook_url": "https://hooks.slack.com/r1"},
                {"type": "webhook", "url": "https://example.com/hook"},
            ]
        )

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        from alerting import config as cfg

        with patch.object(cfg, "get_matching_rules", return_value=[rule]):
            with patch.object(cfg, "update_last_alerted"):
                with patch(
                    "alerting.notifier.SlackBackend.send",
                    side_effect=RuntimeError("slack down"),
                ):
                    with patch("alerting.notifier.WebhookBackend.send") as mock_webhook:
                        self._notifier().fire(_make_golden_record())

        mock_webhook.assert_called_once()

    @patch("alerting.notifier.psycopg2.connect")
    def test_fire_skips_rule_with_no_valid_backends(self, mock_connect):
        rule = _make_rule(channels=[{"type": "unknown_type"}])

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        from alerting import config as cfg

        with patch.object(cfg, "get_matching_rules", return_value=[rule]):
            with patch.object(cfg, "update_last_alerted") as mock_stamp:
                self._notifier().fire(_make_golden_record())

        mock_stamp.assert_not_called()

    @patch("alerting.notifier.psycopg2.connect")
    def test_fire_handles_db_connection_error_gracefully(self, mock_connect):
        mock_connect.side_effect = Exception("DB unreachable")
        # Must not raise — alerting failures are never propagated
        self._notifier().fire(_make_golden_record())

    @patch("alerting.notifier.psycopg2.connect")
    def test_fire_does_nothing_when_no_matching_rules(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        from alerting import config as cfg

        with patch.object(cfg, "get_matching_rules", return_value=[]):
            with patch("alerting.notifier.SlackBackend.send") as mock_send:
                self._notifier().fire(_make_golden_record())

        mock_send.assert_not_called()

    @patch("alerting.notifier.psycopg2.connect")
    def test_fire_multiple_rules_each_get_stamped(self, mock_connect):
        rule_a = _make_rule(id="rule-a")
        rule_b = _make_rule(id="rule-b")

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        from alerting import config as cfg

        with patch.object(cfg, "get_matching_rules", return_value=[rule_a, rule_b]):
            with patch.object(cfg, "update_last_alerted") as mock_stamp:
                with patch("alerting.notifier.SlackBackend.send"):
                    self._notifier().fire(_make_golden_record())

        assert mock_stamp.call_count == 2
        stamped_ids = {c.args[1] for c in mock_stamp.call_args_list}
        assert stamped_ids == {"rule-a", "rule-b"}


# ── _row_to_rule helper ───────────────────────────────────────────────────────


class TestRowToRule:
    def test_parses_jsonb_channels_as_list(self):
        row = {
            "id": "abc",
            "topic_cluster": "*",
            "min_mpi": "0.720",
            "min_signal_count": 1,
            "suppression_minutes": 30,
            "channels": [{"type": "slack", "webhook_url": "x"}],
            "enabled": True,
            "last_alerted_at": None,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
        rule = _row_to_rule(row)
        assert rule.channels == [{"type": "slack", "webhook_url": "x"}]

    def test_parses_channels_from_json_string(self):
        row = {
            "id": "abc",
            "topic_cluster": "*",
            "min_mpi": "0.720",
            "min_signal_count": 1,
            "suppression_minutes": 30,
            "channels": json.dumps([{"type": "webhook", "url": "https://example.com"}]),
            "enabled": True,
            "last_alerted_at": None,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
        rule = _row_to_rule(row)
        assert rule.channels[0]["url"] == "https://example.com"

    def test_handles_null_min_mpi(self):
        row = {
            "id": "abc",
            "topic_cluster": "*",
            "min_mpi": None,
            "min_signal_count": 1,
            "suppression_minutes": 30,
            "channels": [],
            "enabled": True,
            "last_alerted_at": None,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
        rule = _row_to_rule(row)
        assert rule.min_mpi == pytest.approx(0.0)
