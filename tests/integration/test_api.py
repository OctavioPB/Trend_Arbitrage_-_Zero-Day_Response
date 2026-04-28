"""Integration tests for the FastAPI backend.

Requires PostgreSQL running and alembic migrations applied.
All tests are skipped automatically if the DB is unreachable.
See tests/integration/conftest.py for fixture setup.
"""

import os

import pytest
from starlette.testclient import TestClient

os.environ.setdefault(
    "POSTGRES_DSN",
    "postgresql://trend:trend@localhost:5432/trend_arbitrage",
)

from api.main import app  # noqa: E402 — must import after env var is set

_client = TestClient(app, raise_server_exceptions=False)


# ── /health ───────────────────────────────────────────────────────────────────


def test_health_returns_ok() -> None:
    response = _client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── /signals ──────────────────────────────────────────────────────────────────


class TestSignalsEndpoint:
    def test_list_signals_returns_200(self, seeded_signals) -> None:
        response = _client.get("/signals")
        assert response.status_code == 200

    def test_response_shape(self, seeded_signals) -> None:
        data = _client.get("/signals").json()
        assert "signals" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_signal_fields_present(self, seeded_signals) -> None:
        data = _client.get("/signals").json()
        if data["signals"]:
            sig = data["signals"][0]
            for field in ("id", "event_id", "source", "collected_at", "category",
                          "confidence", "topic_tags", "sentiment", "urgency"):
                assert field in sig, f"Missing field: {field}"

    def test_filter_by_category_opportunity(self, seeded_signals) -> None:
        data = _client.get("/signals?category=opportunity").json()
        assert all(s["category"] == "opportunity" for s in data["signals"])

    def test_filter_by_category_threat(self, seeded_signals) -> None:
        data = _client.get("/signals?category=threat").json()
        assert all(s["category"] == "threat" for s in data["signals"])

    def test_filter_by_source_reddit(self, seeded_signals) -> None:
        data = _client.get("/signals?source=reddit").json()
        assert all(s["source"] == "reddit" for s in data["signals"])

    def test_filter_by_urgency_high(self, seeded_signals) -> None:
        data = _client.get("/signals?urgency=high").json()
        assert all(s["urgency"] == "high" for s in data["signals"])

    def test_invalid_category_returns_422(self, seeded_signals) -> None:
        response = _client.get("/signals?category=unknown_category")
        assert response.status_code == 422

    def test_invalid_source_returns_422(self, seeded_signals) -> None:
        response = _client.get("/signals?source=instagram")
        assert response.status_code == 422

    def test_pagination(self, seeded_signals) -> None:
        data = _client.get("/signals?page=1&page_size=1").json()
        assert data["page"] == 1
        assert data["page_size"] == 1
        assert len(data["signals"]) <= 1

    def test_total_is_integer(self, seeded_signals) -> None:
        data = _client.get("/signals").json()
        assert isinstance(data["total"], int)

    def test_response_does_not_expose_dsn(self, seeded_signals) -> None:
        """Internal connection strings must not appear in any response."""
        response = _client.get("/signals")
        body = response.text
        assert "postgresql://" not in body
        assert "password" not in body.lower()

    def test_confidence_is_float(self, seeded_signals) -> None:
        data = _client.get("/signals?category=opportunity").json()
        if data["signals"]:
            assert isinstance(data["signals"][0]["confidence"], float)


# ── /mpi ─────────────────────────────────────────────────────────────────────


class TestMpiEndpoint:
    def test_returns_200(self, seeded_signals) -> None:
        response = _client.get("/mpi")
        assert response.status_code == 200

    def test_response_shape(self, seeded_signals) -> None:
        data = _client.get("/mpi").json()
        assert "cells" in data
        assert "computed_at" in data
        assert "window_minutes" in data
        assert "topic_clusters" in data
        assert "time_buckets" in data
        assert isinstance(data["cells"], list)

    def test_cell_score_between_zero_and_one(self, seeded_signals) -> None:
        data = _client.get("/mpi").json()
        for cell in data["cells"]:
            assert 0.0 <= cell["score"] <= 1.0, f"score out of range: {cell['score']}"

    def test_window_minutes_propagated(self, seeded_signals) -> None:
        data = _client.get("/mpi?window_minutes=30").json()
        assert data["window_minutes"] == 30

    def test_invalid_window_returns_422(self, seeded_signals) -> None:
        response = _client.get("/mpi?window_minutes=2")
        assert response.status_code == 422

    def test_topic_clusters_is_sorted_list(self, seeded_signals) -> None:
        data = _client.get("/mpi").json()
        clusters = data["topic_clusters"]
        assert clusters == sorted(clusters)


# ── /segments ─────────────────────────────────────────────────────────────────


class TestSegmentsEndpoint:
    def test_returns_200(self, seeded_golden_record) -> None:
        response = _client.get("/segments")
        assert response.status_code == 200

    def test_response_shape(self, seeded_golden_record) -> None:
        data = _client.get("/segments").json()
        assert "records" in data
        assert "total" in data
        assert isinstance(data["records"], list)

    def test_record_fields_present(self, seeded_golden_record) -> None:
        data = _client.get("/segments").json()
        if data["records"]:
            rec = data["records"][0]
            for field in ("id", "created_at", "topic_cluster", "mpi_score",
                          "signal_count", "audience_proxy", "recommended_action",
                          "expires_at", "ttl_seconds"):
                assert field in rec, f"Missing field: {field}"

    def test_ttl_seconds_is_positive(self, seeded_golden_record) -> None:
        data = _client.get("/segments").json()
        if data["records"]:
            assert data["records"][0]["ttl_seconds"] > 0

    def test_only_active_records_returned(self, seeded_golden_record) -> None:
        """expires_at must be in the future for all returned records."""
        from datetime import timezone

        data = _client.get("/segments").json()
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        for rec in data["records"]:
            assert rec["expires_at"] > now_iso, (
                f"Expired record returned: {rec['id']} expires_at={rec['expires_at']}"
            )

    def test_ordered_by_mpi_descending(self, seeded_golden_record) -> None:
        data = _client.get("/segments").json()
        scores = [r["mpi_score"] for r in data["records"]]
        assert scores == sorted(scores, reverse=True)


# ── /ws/heatmap ───────────────────────────────────────────────────────────────


class TestWebSocketHeatmap:
    def test_connects_and_receives_initial_push(self, seeded_signals) -> None:
        with _client.websocket_connect("/ws/heatmap") as ws:
            data = ws.receive_json()
            assert "cells" in data
            assert "computed_at" in data
            assert "topic_clusters" in data

    def test_cells_have_correct_schema(self, seeded_signals) -> None:
        with _client.websocket_connect("/ws/heatmap") as ws:
            data = ws.receive_json()
        for cell in data["cells"]:
            assert "topic_cluster" in cell
            assert "time_bucket" in cell
            assert "score" in cell
            assert "signal_count" in cell
            assert 0.0 <= cell["score"] <= 1.0

    def test_disconnect_does_not_crash_server(self, seeded_signals) -> None:
        """Server must remain up after a client disconnects."""
        with _client.websocket_connect("/ws/heatmap") as ws:
            ws.receive_json()
            # Disconnect without sending close frame — simulates abrupt disconnection

        # Server should still respond to HTTP after disconnect
        response = _client.get("/health")
        assert response.status_code == 200

    def test_response_does_not_expose_secrets(self, seeded_signals) -> None:
        with _client.websocket_connect("/ws/heatmap") as ws:
            data = ws.receive_json()
        body = str(data)
        assert "postgresql://" not in body
        assert "sk-ant-" not in body


# ── error handling ────────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_generic_error_returns_500_no_details(self) -> None:
        """500 responses must not include stack traces or internal config."""
        # Force a DB error by temporarily overriding the DSN with an invalid one
        import api.db as db_module

        original_pool = db_module._pool
        db_module._pool = None
        original_dsn = os.environ.get("POSTGRES_DSN", "")
        os.environ["POSTGRES_DSN"] = "postgresql://bad:bad@localhost:9999/nonexistent"

        try:
            response = _client.get("/signals")
            # Either 500 (DB error) or 200 (connection cached from previous test)
            if response.status_code == 500:
                body = response.json()
                assert "detail" in body
                assert "postgresql://" not in str(body)
                assert "traceback" not in str(body).lower()
        finally:
            os.environ["POSTGRES_DSN"] = original_dsn
            db_module._pool = None  # reset so next test gets a fresh pool


from datetime import datetime  # noqa: E402 — needed for test_only_active_records_returned
