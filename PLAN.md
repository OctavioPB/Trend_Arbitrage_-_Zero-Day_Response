# Trend Arbitrage & Zero-Day Response System — Sprint Plan

## Overview

This plan breaks the build into 6 sprints of approximately 1–2 weeks each, following the recommended build order in `CLAUDE.md`. Each sprint has a clear goal, deliverables, acceptance criteria, and dependencies.

---

## Sprint 1 — Infrastructure & Local Environment

**Goal:** Every developer can run the full infrastructure stack locally with a single command. No application code yet — just verified plumbing.

**Duration:** 1 week

### Deliverables

- `docker-compose.yml` with services: Apache Kafka, Zookeeper, PostgreSQL, Redis, Apache Airflow (webserver + scheduler + worker)
- `.env.example` with all variables documented (see Environment Variables in `CLAUDE.md`)
- `alembic/` initialized; baseline migration creating `enriched_signals` and `golden_records` tables
- `config/mpi_weights.json` with default weights (`volume: 0.4`, `velocity: 0.35`, `sentiment: 0.25`)
- `README.md` — local dev quickstart (clone → copy `.env` → `docker-compose up -d`)

### Acceptance Criteria

- `docker-compose up -d` starts cleanly with no errors
- Kafka topic `raw_signals` and `enriched_signals` can be created via CLI
- Airflow UI is reachable at `localhost:8080`
- PostgreSQL schema migrations run without errors (`alembic upgrade head`)
- Redis ping returns `PONG`

### Dependencies

None — this is the foundation.

---

## Sprint 2 — Ingestion Layer (Kafka Producers)

**Goal:** Real data flows from Reddit, Twitter/X, and the scraper into Kafka's `raw_signals` topic reliably and idempotently.

**Duration:** 1–2 weeks

### Deliverables

- `ingestion/config/kafka_config.py` — shared Kafka client config, retry logic, connection failure handling
- `ingestion/producers/reddit_producer.py` — polls subreddits via `praw` every 90 seconds; publishes raw event JSON
- `ingestion/producers/twitter_producer.py` — filtered stream (v2 API) on competitor handles + brand keywords
- `ingestion/producers/scraper_producer.py` — Playwright headless; respects `robots.txt`; randomized 3–8s delays
- `ingestion/consumers/raw_event_consumer.py` — basic consumer for verification/logging only (not the ETL path)
- Unit tests: `tests/unit/test_producers.py` — mock Kafka client; verify event schema and idempotency

### Acceptance Criteria

- All three producers publish valid raw event JSON matching the schema in `CLAUDE.md`
- `event_id` (UUID4) is present and unique; re-running a producer does not produce duplicate event IDs for the same source content
- Kafka consumer can read from `raw_signals` and print events to stdout
- Producer failures (network down, API rate limit) are caught and retried with exponential backoff; ingestion does not crash
- No API keys or secrets appear in logs

### Dependencies

Sprint 1 complete (Kafka running).

---

## Sprint 3 — Semantic ETL (Airflow + LLM Classification)

**Goal:** Raw signals are classified by Claude into opportunity / threat / noise with structured metadata and persisted to PostgreSQL.

**Duration:** 2 weeks

### Deliverables

- `etl/prompts/classification_prompt.txt` — system prompt for the classifier (never hardcoded in Python)
- `etl/tasks/llm_classifier.py` — async batch classifier using `anthropic.AsyncAnthropic`; batches of 20; exponential backoff on 429s; fallback category `"noise"` on parse failure
- `etl/tasks/entity_extractor.py` — extracts topic tags and audience proxy attributes from enriched signals
- `etl/tasks/deduplicator.py` — deduplicates by `event_id` before DB write
- `etl/dags/semantic_enrichment_dag.py` — Airflow DAG scheduled every 5 minutes; reads from `raw_signals` topic, enriches, writes to `enriched_signals` table and `enriched_signals` Kafka topic
- `etl/dags/golden_record_dag.py` — stub only (wired in Sprint 4)
- Unit tests: `tests/unit/test_llm_classifier.py` — mocked Anthropic API; tests JSON validation, fallback behavior, confidence logging

### Acceptance Criteria

- Classifier processes a batch of 20 sample signals and returns valid classification JSON for each
- Invalid or malformed LLM responses do not crash the pipeline; they fall back to `category: "noise"` and are logged
- Signals with `confidence < 0.6` are flagged in the database (not discarded)
- `enriched_signals` table rows contain all fields from the schema in `CLAUDE.md`
- Airflow DAG is visible in the UI, runs on schedule, and shows task success/failure correctly
- All LLM calls use the model string from `LLM_MODEL` env var, not a hardcoded value

### Dependencies

Sprints 1 and 2 complete (Kafka producing data; DB schema migrated).

---

## Sprint 4 — Predictive Processing (MPI + Golden Records)

**Goal:** The Market Pressure Index is calculated per topic cluster on a rolling window, and Golden Records are automatically generated when the MPI threshold is crossed.

**Duration:** 1–2 weeks

### Deliverables

- `predictive/mpi_calculator.py` — rolling MPI formula using weights from `config/mpi_weights.json`; no hardcoded weights
- `predictive/threshold_monitor.py` — polls MPI scores every 5 minutes; triggers golden record generation when `MPI >= MPI_THRESHOLD`
- `predictive/golden_record_generator.py` — queries enriched signals, builds audience proxy JSONB, writes `golden_records` row, publishes `golden_record_ready` event to Kafka; computes `expires_at` from velocity decay (not a fixed offset)
- `etl/dags/golden_record_dag.py` — wired DAG that calls the generator on threshold breach
- `config/mpi_weights.json` — finalized with tunable weights structure
- Unit tests: `tests/unit/test_mpi_calculator.py` — formula tested with synthetic data covering edge cases (zero volume, all-negative sentiment, velocity cliff)

### Acceptance Criteria

- MPI score for a topic cluster falls between 0.0 and 1.0 under all input conditions
- Changing weights in `config/mpi_weights.json` (without code changes) produces different MPI outputs
- A Golden Record is written to the DB and a `golden_record_ready` event published to Kafka when MPI crosses the threshold
- `expires_at` is not a fixed offset from `created_at` — it varies with topic velocity
- All three MPI component scores (`volume_score`, `velocity_score`, `sentiment_score`) are logged for observability
- Unit tests pass with 100% coverage of the MPI formula branches

### Dependencies

Sprint 3 complete (enriched signals in PostgreSQL).

---

## Sprint 5 — Backend API (FastAPI)

**Goal:** A FastAPI backend exposes enriched signals, MPI scores, and Golden Records via REST and pushes live heat map data to the dashboard over WebSocket.

**Duration:** 1 week

### Deliverables

- `api/schemas/models.py` — Pydantic models for all request/response shapes
- `api/routers/signals.py` — REST endpoints: list enriched signals (filter by category, urgency, date range)
- `api/routers/mpi.py` — REST endpoint: current MPI grid (all topic clusters × time buckets)
- `api/routers/segments.py` — REST endpoint: list active Golden Records with audience proxy and `expires_at`
- `api/main.py` — FastAPI app wiring; `/ws/heatmap` WebSocket endpoint pushing MPI grid every 60 seconds; client reconnect handled gracefully
- Integration tests: `tests/integration/test_api.py` — tests against live DB (testcontainers); covers REST endpoints and WebSocket push

### Acceptance Criteria

- All REST endpoints return correct data shapes matching Pydantic schemas
- `/ws/heatmap` pushes an updated MPI grid every 60 seconds without client polling
- WebSocket disconnects are handled gracefully; clients can reconnect without server restart
- API does not expose raw API keys, internal connection strings, or unfiltered stack traces in error responses
- Integration tests pass with Docker services running

### Dependencies

Sprints 3 and 4 complete (data exists in DB; MPI and Golden Records being generated).

---

## Sprint 6 — Dashboard & End-to-End Validation

**Goal:** The React heat map dashboard is live, data flows end-to-end from social APIs to the UI, and the system is validated with a realistic load test.

**Duration:** 1–2 weeks

### Deliverables

- `dashboard/src/components/HeatMap.jsx` — WebSocket-driven heat map; X = topic cluster, Y = 5-minute time buckets (last 60 min); cell color = MPI score (viridis/inferno colormap); cell pulse animation = velocity
- `dashboard/src/components/TrendCard.jsx` — displays a single Golden Record with topic, MPI score, recommended action, and live `expires_at` countdown
- `dashboard/src/components/MpiGauge.jsx` — per-cluster MPI gauge widget
- `dashboard/src/App.jsx` — layout wiring; WebSocket connection management; auto-reconnect
- `dashboard/package.json` — dependencies pinned
- `tests/integration/test_e2e_pipeline.py` — seeds a Kafka topic with 50 synthetic raw events; asserts that enriched signals appear in DB, MPI is calculated, a Golden Record is generated, and the WebSocket pushes an updated heat map within 5 minutes

### Acceptance Criteria

- Heat map refreshes from WebSocket data only — no REST polling from the frontend
- Heat map shows only the last 60 minutes of data (no historical view, no week-over-week comparisons)
- Sidebar shows top 5 active Golden Records with live countdown to expiry
- Color encoding is perceptually uniform (viridis or inferno); no categorical color scale
- End-to-end integration test passes: synthetic signals → enriched → MPI → Golden Record → WebSocket push
- Dashboard renders correctly when there are zero active signals (empty state, no crashes)

### Dependencies

All previous sprints complete.

---

## Milestone Summary

| Sprint | Theme | Key Output | Duration |
|--------|-------|-----------|----------|
| 1 | Infrastructure | `docker-compose.yml`, DB migrations, local stack running | 1 week |
| 2 | Ingestion | Reddit, Twitter, scraper producers publishing to Kafka | 1–2 weeks |
| 3 | Semantic ETL | Airflow DAG + LLM classifier writing enriched signals to DB | 2 weeks |
| 4 | Predictive Engine | MPI calculator + Golden Record generator | 1–2 weeks |
| 5 | Backend API | FastAPI REST + WebSocket `/ws/heatmap` | 1 week |
| 6 | Dashboard + E2E | React heat map + end-to-end pipeline validation | 1–2 weeks |

**Total estimated duration:** 7–10 weeks

---

## Cross-Sprint Standards (Applies Throughout)

- Python 3.11+; `ruff` for linting, `black` for formatting, type hints on all public functions
- All PostgreSQL schema changes via `alembic` migrations — no manual `ALTER TABLE`
- Secrets in `.env` only; never logged, never committed
- All Kafka producers/consumers handle connection failures with retry + exponential backoff
- LLM classification responses validated before DB write; invalid responses fall back to `"noise"`
- MPI weights and `MPI_THRESHOLD` configurable without code deploy

---

## Out of Scope (v1)

The following are explicitly excluded from all sprints per `CLAUDE.md`:

- Paid ad platform integration (Google Ads, Meta Ads API)
- Historical trend analysis or BI reporting
- Multi-tenant support
- Dashboard authentication