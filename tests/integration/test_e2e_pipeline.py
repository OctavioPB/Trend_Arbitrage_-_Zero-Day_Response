"""End-to-end integration test for the Trend Arbitrage pipeline.

Coverage:
    enriched_signals in DB → /mpi API → /segments API → /ws/heatmap push

The Kafka → Airflow → DB path is validated separately by TestKafkaWritable,
which only checks that topics accept writes (Airflow scheduling is not
automated in tests — it requires a live Airflow scheduler).

All tests skip automatically if PostgreSQL is not reachable.
Kafka tests skip if Kafka is not reachable.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

os.environ.setdefault(
    "POSTGRES_DSN",
    "postgresql://trend:trend@localhost:5432/trend_arbitrage",
)

from api.main import app  # noqa: E402 — must import after env var is set
from starlette.testclient import TestClient

_client = TestClient(app, raise_server_exceptions=False)

_DSN = os.environ.get("POSTGRES_DSN", "postgresql://trend:trend@localhost:5432/trend_arbitrage")

_SEED_TOPICS = [
    "ai-investment",
    "competitor-pricing",
    "crypto-trend",
    "market-volatility",
    "tech-layoffs",
]


# ── Reachability helpers ──────────────────────────────────────────────────────


def _db_reachable() -> bool:
    try:
        conn = psycopg2.connect(_DSN, connect_timeout=3)
        conn.close()
        return True
    except psycopg2.OperationalError:
        return False


def _kafka_reachable() -> bool:
    try:
        from kafka import KafkaProducer
        from kafka.errors import NoBrokersAvailable  # noqa: F401

        p = KafkaProducer(
            bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            request_timeout_ms=3000,
        )
        p.close()
        return True
    except Exception:
        return False


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def db_conn():
    """Module-scoped DB connection; skips if PostgreSQL is unreachable."""
    if not _db_reachable():
        pytest.skip("PostgreSQL not available — run 'docker-compose up -d' first")
    conn = psycopg2.connect(_DSN)
    conn.autocommit = False
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def seeded_50_signals(db_conn):
    """Insert 50 synthetic enriched signals across 5 topic clusters.

    Signals are spread across the last 55 minutes to produce non-empty
    MPI time buckets. Cleanup removes them after the module finishes.
    """
    now = datetime.now(tz=timezone.utc)
    test_ids: list[str] = []

    insert_sql = """
        INSERT INTO enriched_signals
            (event_id, source, collected_at, category, confidence, topic_tags,
             sentiment, urgency, engagement_score, url, reasoning)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id::text
    """

    with db_conn.cursor() as cur:
        for i in range(50):
            topic = _SEED_TOPICS[i % len(_SEED_TOPICS)]
            collected_at = now - timedelta(minutes=(i % 55))
            tags = [topic] if i % 4 else [topic, f"{topic}-sub"]
            cur.execute(
                insert_sql,
                (
                    str(uuid.uuid4()),
                    ["reddit", "twitter", "scraper"][i % 3],
                    collected_at,
                    ["opportunity", "threat"][i % 2],
                    round(0.65 + (i % 4) * 0.08, 3),
                    tags,
                    ["positive", "negative", "neutral"][i % 3],
                    ["low", "medium", "high"][i % 3],
                    float(50 + i * 10),
                    f"https://example.com/signal/{i}",
                    f"Synthetic E2E signal {i} for topic {topic}.",
                ),
            )
            test_ids.append(cur.fetchone()[0])
    db_conn.commit()

    yield test_ids

    with db_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM enriched_signals WHERE id = ANY(%s::uuid[])",
            (test_ids,),
        )
    db_conn.commit()


@pytest.fixture(scope="module")
def seeded_e2e_golden_record(db_conn):
    """Insert a Golden Record for use in E2E segment tests."""
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=3)

    insert_sql = """
        INSERT INTO golden_records
            (topic_cluster, mpi_score, signal_count, audience_proxy,
             recommended_action, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id::text
    """
    with db_conn.cursor() as cur:
        cur.execute(
            insert_sql,
            (
                "ai-investment",
                0.81,
                10,
                json.dumps({"subreddits": ["r/investing"], "top_topics": ["ai-investment"]}),
                "Prepare bid segment for AI investment keywords before saturation.",
                expires_at,
            ),
        )
        record_id = cur.fetchone()[0]
    db_conn.commit()

    yield record_id

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM golden_records WHERE id = %s::uuid", (record_id,))
    db_conn.commit()


# ── /mpi with real data ───────────────────────────────────────────────────────


class TestMpiWithSyntheticData:
    def test_mpi_returns_non_empty_cells(self, seeded_50_signals) -> None:
        data = _client.get("/mpi").json()
        assert data["cells"], "MPI should return cells when enriched signals exist"

    def test_mpi_topic_clusters_include_seeded_topics(self, seeded_50_signals) -> None:
        data = _client.get("/mpi").json()
        actual = set(data["topic_clusters"])
        expected = set(_SEED_TOPICS)
        overlap = actual & expected
        assert overlap, f"Expected at least one seeded topic cluster, got: {actual}"

    def test_all_cell_scores_bounded(self, seeded_50_signals) -> None:
        data = _client.get("/mpi").json()
        for cell in data["cells"]:
            assert 0.0 <= cell["score"] <= 1.0, f"Score out of [0,1]: {cell}"

    def test_aggregate_signal_count_reflects_seeded_volume(self, seeded_50_signals) -> None:
        data = _client.get("/mpi").json()
        total = sum(c["signal_count"] for c in data["cells"])
        assert total >= 40, f"Expected >= 40 signals across grid, got {total}"

    def test_time_buckets_within_60min_window(self, seeded_50_signals) -> None:
        data = _client.get("/mpi?window_minutes=60").json()
        now = datetime.now(tz=timezone.utc)
        cutoff_iso = (now - timedelta(minutes=60)).isoformat()
        for tb in data["time_buckets"]:
            assert tb >= cutoff_iso, f"Time bucket {tb} is outside the 60-min window"

    def test_window_minutes_param_propagated(self, seeded_50_signals) -> None:
        data = _client.get("/mpi?window_minutes=30").json()
        assert data["window_minutes"] == 30

    def test_signals_endpoint_returns_seeded_signals(self, seeded_50_signals) -> None:
        data = _client.get("/signals?page_size=100").json()
        returned_ids = {s["id"] for s in data["signals"]}
        assert returned_ids & set(seeded_50_signals), (
            "Seeded signal IDs should appear in /signals response"
        )

    def test_signals_filter_by_category_works(self, seeded_50_signals) -> None:
        opps = _client.get("/signals?category=opportunity&page_size=100").json()
        threats = _client.get("/signals?category=threat&page_size=100").json()
        assert all(s["category"] == "opportunity" for s in opps["signals"])
        assert all(s["category"] == "threat" for s in threats["signals"])


# ── /segments with Golden Record ─────────────────────────────────────────────


class TestSegmentsE2E:
    def test_segments_returns_seeded_record(self, seeded_e2e_golden_record) -> None:
        data = _client.get("/segments").json()
        ids = {r["id"] for r in data["records"]}
        assert seeded_e2e_golden_record in ids, (
            f"Expected golden record {seeded_e2e_golden_record} in /segments response"
        )

    def test_mpi_score_matches_inserted_value(self, seeded_e2e_golden_record) -> None:
        data = _client.get("/segments").json()
        rec = next((r for r in data["records"] if r["id"] == seeded_e2e_golden_record), None)
        assert rec is not None
        assert abs(rec["mpi_score"] - 0.81) < 0.001

    def test_ttl_seconds_is_positive(self, seeded_e2e_golden_record) -> None:
        data = _client.get("/segments").json()
        rec = next((r for r in data["records"] if r["id"] == seeded_e2e_golden_record), None)
        assert rec is not None
        assert rec["ttl_seconds"] > 0, "Record should have positive TTL (expires in ~3h)"

    def test_segments_ordered_by_mpi_descending(self, seeded_e2e_golden_record) -> None:
        data = _client.get("/segments").json()
        scores = [r["mpi_score"] for r in data["records"]]
        assert scores == sorted(scores, reverse=True)

    def test_audience_proxy_is_dict(self, seeded_e2e_golden_record) -> None:
        data = _client.get("/segments").json()
        rec = next((r for r in data["records"] if r["id"] == seeded_e2e_golden_record), None)
        assert rec is not None
        assert isinstance(rec["audience_proxy"], dict)
        assert "subreddits" in rec["audience_proxy"]


# ── /ws/heatmap with live data ────────────────────────────────────────────────


class TestWebSocketE2E:
    def test_websocket_push_contains_seeded_clusters(self, seeded_50_signals) -> None:
        with _client.websocket_connect("/ws/heatmap") as ws:
            data = ws.receive_json()
        actual_clusters = set(data.get("topic_clusters", []))
        expected = set(_SEED_TOPICS)
        assert actual_clusters & expected, (
            f"Expected at least one seeded cluster in WS push. Got: {actual_clusters}"
        )

    def test_websocket_cells_have_correct_structure(self, seeded_50_signals) -> None:
        with _client.websocket_connect("/ws/heatmap") as ws:
            data = ws.receive_json()
        for cell in data.get("cells", []):
            assert "topic_cluster" in cell
            assert "time_bucket" in cell
            assert "score" in cell
            assert "signal_count" in cell
            assert 0.0 <= cell["score"] <= 1.0

    def test_websocket_push_after_disconnect_does_not_crash_server(
        self, seeded_50_signals
    ) -> None:
        with _client.websocket_connect("/ws/heatmap") as ws:
            ws.receive_json()
            # Abrupt disconnect

        response = _client.get("/health")
        assert response.status_code == 200


# ── Kafka topic writability ───────────────────────────────────────────────────


class TestKafkaWritable:
    """Verify that Kafka topics accept writes — entry point of the full pipeline.

    Airflow processing (raw_signals → enriched_signals) is excluded from
    automated tests since it requires a live Airflow scheduler.
    """

    def test_raw_signals_topic_accepts_writes(self) -> None:
        if not _kafka_reachable():
            pytest.skip("Kafka not available")

        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

        from ingestion.config.kafka_config import create_producer, publish_with_retry
        from ingestion.models import RawEvent, make_event_id

        producer = create_producer()
        event = RawEvent(
            event_id=make_event_id("reddit", f"e2e-test-{uuid.uuid4()}"),
            source="reddit",
            collected_at=datetime.now(tz=timezone.utc),
            raw_text="End-to-end pipeline smoke test signal.",
            url="https://reddit.com/r/test/comments/e2e",
            author="e2e_test",
            engagement_score=1.0,
        )
        publish_with_retry(
            producer,
            topic=os.environ.get("KAFKA_TOPIC_RAW", "raw_signals"),
            payload=event.to_kafka_payload(),
            key=event.event_id,
        )
        producer.flush(timeout=10)
        producer.close()

    def test_enriched_signals_topic_accepts_writes(self) -> None:
        if not _kafka_reachable():
            pytest.skip("Kafka not available")

        from kafka import KafkaProducer

        producer = KafkaProducer(
            bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        producer.send(
            os.environ.get("KAFKA_TOPIC_ENRICHED", "enriched_signals"),
            value={"test": True, "event_id": str(uuid.uuid4())},
        )
        producer.flush(timeout=10)
        producer.close()
