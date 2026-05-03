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
| F1 | Alerting | Slack + webhook push when MPI crosses threshold | 1 week |
| F2 | Historical Trends | TimescaleDB archive, baseline calibration, trend persistence | 1–2 weeks |
| F3 | Ingestion Expansion | LinkedIn, NewsAPI, RSS feeds; source-weight config | 1–2 weeks |
| F4 | Auth & API Security | JWT auth, API key management, rate limiting, RBAC | 1–2 weeks |
| F5 | Ad Platform Integration | Push audiences to Google Ads + Meta | 2 weeks |
| F6 | Playbook Engine | Rules-based automated actions triggered by Golden Records | 2 weeks |
| F7 | Feedback Loop | Conversion tracking, threshold auto-calibration | 2 weeks |
| F8 | Stream Processing | Replace Airflow batch with Kafka Streams (sub-30s latency) | 2–3 weeks |

**Total estimated duration:** 7–10 weeks (v1) + 14–19 weeks (F1–F8)

---

---

## Future Implementations (F1–F8)

These sprints extend the v1 system into a production-grade, closed-loop marketing intelligence platform. Each is independent enough to be prioritized individually, but F4 → F5 → F6 → F7 must run in order.

---

## F1 — Real-time Alerting (Slack + Webhooks)

**Goal:** Marketing teams are notified within 60 seconds of a Golden Record being generated — without requiring anyone to watch the dashboard.

**Duration:** 1 week

### Deliverables

- `alerting/notifier.py` — `AlertNotifier` class with pluggable backends: `SlackBackend`, `WebhookBackend`, `EmailBackend` (SMTP)
- `alerting/config.py` — alert rules: minimum MPI score, minimum signal count, per-topic suppression window (prevents duplicate alerts within N minutes)
- `etl/dags/golden_record_dag.py` — updated to call `AlertNotifier.fire()` after each Golden Record write
- `api/routers/alerts.py` — `POST /alerts/config` endpoint to update alert rules at runtime without a code deploy
- `alembic/versions/002_alert_rules.py` — `alert_rules` table: `topic_cluster`, `min_mpi`, `suppression_minutes`, `channels` (JSONB)
- Unit tests: `tests/unit/test_notifier.py` — mock all three backends; test suppression window, threshold filtering, payload shape

### Acceptance Criteria

- Slack message arrives within 60 seconds of a Golden Record write when MPI ≥ configured threshold
- Duplicate alerts for the same topic cluster are suppressed for the configured window
- Webhook payload matches a documented schema (topic, mpi_score, recommended_action, expires_at, dashboard_url)
- Alert rules can be updated via the API endpoint without restarting any service
- No API keys or DSNs appear in alert payloads or logs

### Dependencies

Sprint 6 complete (Golden Record pipeline running end-to-end).

---

## F2 — Historical Trend Memory (MPI Archive)

**Goal:** MPI scores are persisted as a time series, enabling real historical baselines, week-over-week comparisons, and trend persistence detection — replacing the synthetic `baseline_avg_signals=10` placeholder.

**Duration:** 1–2 weeks

### Deliverables

- `alembic/versions/003_mpi_history.py` — `mpi_history` table: `recorded_at TIMESTAMPTZ`, `topic_cluster TEXT`, `mpi_score NUMERIC(4,3)`, `signal_count INT`, `window_minutes INT`; hypertable if TimescaleDB is available, plain table otherwise
- `predictive/mpi_archiver.py` — writes one row per topic cluster per MPI computation cycle; idempotent on `(recorded_at_bucket, topic_cluster)`
- `predictive/mpi_calculator.py` — updated `calculate_mpi()` to read `baseline_avg_signals` from the 7-day rolling average in `mpi_history` instead of a hardcoded constant
- `api/routers/history.py` — `GET /history/mpi?cluster=X&from_dt=Y&to_dt=Z` returning time-series MPI data; used by future analytics views
- `etl/dags/golden_record_dag.py` — updated to call archiver after each MPI computation
- Unit tests: `tests/unit/test_mpi_archiver.py` — idempotency, baseline fallback when history < 24h, response shape

### Acceptance Criteria

- Every MPI computation cycle writes one archive row per active topic cluster
- After 7 days of data, `baseline_avg_signals` in `calculate_mpi()` is sourced from real history, not a constant
- `GET /history/mpi` returns time-series data sortable by `recorded_at`
- Inserting the same `(recorded_at_bucket, topic_cluster)` twice does not create a duplicate row
- Dashboard heat map is unaffected — no breaking changes to `/mpi` or `/ws/heatmap`

### Dependencies

Sprint 6 complete.

---

## F3 — Ingestion Expansion (LinkedIn + News + RSS)

**Goal:** Signal coverage expands beyond Reddit and Twitter to include professional networks, news aggregators, and competitor press release feeds — reducing blind spots in B2B market segments.

**Duration:** 1–2 weeks

### Deliverables

- `ingestion/producers/linkedin_producer.py` — polls LinkedIn via RapidAPI (unofficial) for company posts and trending topics; falls back to RSS feed scraping if API quota is exhausted
- `ingestion/producers/news_producer.py` — NewsAPI + GDELT integration; filters by competitor names, industry keywords, and configurable topic seed list
- `ingestion/producers/rss_producer.py` — generic RSS/Atom feed consumer; target list in `config/rss_feeds.json`
- `config/rss_feeds.json` — seed list of competitor blogs, industry publications, and job board RSS feeds (job postings as leading indicator)
- `config/source_weights.json` — per-source signal weight applied during MPI calculation: `{"reddit": 1.0, "twitter": 0.9, "news": 1.2, "linkedin": 1.1, "rss": 0.7}`; readable by `mpi_calculator.py`
- `ingestion/models.py` — `source` Literal extended to include `"linkedin"`, `"news"`, `"rss"`
- `alembic/versions/004_source_weights.py` — adds `source_weight NUMERIC(3,2) DEFAULT 1.0` to `enriched_signals`
- Unit tests: `tests/unit/test_news_producer.py` — schema validation, deduplication by URL hash, source weight propagation

### Acceptance Criteria

- All three new producers publish valid `RawEvent` JSON to `raw_signals` with correct `source` values
- Source weight from `config/source_weights.json` is applied to the MPI volume score without code changes
- Changing a weight in `source_weights.json` changes MPI output without a service restart
- No duplicate events for the same URL across polling cycles
- RSS feeds with invalid XML are caught and logged; the producer does not crash

### Dependencies

Sprint 2 complete (Kafka ingestion patterns established).

---

## F4 — Authentication & API Security

**Goal:** The API is safe to expose outside the internal network. External consumers (ad platforms, BI tools) can authenticate with scoped API keys. The dashboard requires login.

**Duration:** 1–2 weeks

### Deliverables

- `api/auth.py` — JWT token issuance and validation via `python-jose`; `APIKeyHeader` dependency for machine-to-machine consumers; `OAuth2PasswordBearer` for dashboard login
- `alembic/versions/005_api_keys.py` — `api_keys` table: `key_hash TEXT`, `owner TEXT`, `scopes TEXT[]` (`read:signals`, `read:segments`, `write:alerts`), `created_at`, `expires_at`, `last_used_at`
- `api/routers/auth.py` — `POST /auth/token` (user login), `POST /auth/keys` (generate API key), `DELETE /auth/keys/{id}` (revoke)
- `api/middleware/rate_limit.py` — token-bucket rate limiter backed by Redis; configurable per-scope limits via environment variable
- `dashboard/src/` — login page (`LoginPage.jsx`), token storage in `sessionStorage`, `Authorization: Bearer` header on all fetch calls, redirect to login on 401
- Unit tests: `tests/unit/test_auth.py` — token expiry, scope enforcement, rate limit exhaustion, key revocation

### Acceptance Criteria

- All `/signals`, `/mpi`, `/segments` endpoints return 401 without a valid token or API key
- API keys are stored as bcrypt hashes — the plain key is shown only once at creation
- Rate limit returns 429 with `Retry-After` header; limit resets correctly after the window
- Scoped API key with `read:signals` cannot call `POST /alerts/config`
- The dashboard redirects to the login page on session expiry without crashing

### Dependencies

Sprint 6 complete.

---

## F5 — Ad Platform Integration (Google Ads + Meta)

**Goal:** Golden Records automatically push audience definitions to Google Ads customer match and Meta custom audiences, converting intelligence into live campaign adjustments within minutes of a signal spike.

**Duration:** 2 weeks

### Deliverables

- `integrations/google_ads.py` — `GoogleAdsAudienceSync`: reads a Golden Record's `audience_proxy`, maps `top_topics` to keyword lists, updates or creates a Google Ads Customer Match list via `google-ads` Python client
- `integrations/meta_ads.py` — `MetaAudienceSync`: reads `audience_proxy.handles`, creates or updates a Meta Custom Audience via the Marketing API
- `integrations/audience_mapper.py` — translates `audience_proxy` JSONB (subreddits, handles, site sections) to platform-specific audience specs; configurable keyword expansion via `config/audience_mapping.json`
- `config/audience_mapping.json` — maps topic clusters to seed keyword lists per platform
- `etl/dags/golden_record_dag.py` — updated to call both sync functions after each Golden Record write (non-blocking; failures do not roll back the record)
- `alembic/versions/006_audience_sync_log.py` — `audience_sync_log` table: `golden_record_id`, `platform`, `status`, `audience_id`, `synced_at`, `error_message`
- Integration tests: `tests/integration/test_ad_platforms.py` — mock both platform APIs; verify payload shape, retry on 429, sync log write on success and failure

### Acceptance Criteria

- A Golden Record with `audience_proxy` containing at least one subreddit or handle triggers audience sync within 90 seconds
- Platform API failures are logged to `audience_sync_log` with `status=error` and do not crash the DAG
- The same Golden Record does not push duplicate audiences to the same platform (idempotent by `golden_record_id + platform`)
- Audience sync can be disabled per platform via environment variable without code changes
- No ad platform credentials appear in logs or the sync log table

### Dependencies

F4 complete (API security hardened before external integrations). Sprint 4 complete.

---

## F6 — Automated Playbook Engine

**Goal:** When a Golden Record fires above a configurable confidence level, the system executes a pre-defined playbook automatically — no human in the loop required for high-confidence, low-risk actions.

**Duration:** 2 weeks

### Deliverables

- `playbooks/engine.py` — `PlaybookEngine`: evaluates trigger conditions against a Golden Record, selects matching playbooks, executes action steps sequentially; supports dry-run mode
- `playbooks/actions/` — action implementations:
  - `bid_adjustment.py` — increase Google Ads max CPC by configured percentage
  - `content_brief.py` — POST to a configured webhook with a structured content brief (topic, angle, urgency, audience)
  - `slack_escalation.py` — pages a human for review when MPI > 0.9 (high-confidence, escalation rather than automation)
- `config/playbooks.json` — playbook definitions: trigger conditions (`min_mpi`, `topic_cluster_pattern`, `urgency`), action list, cooldown window
- `alembic/versions/007_playbook_runs.py` — `playbook_runs` table: `golden_record_id`, `playbook_name`, `actions_taken` (JSONB), `dry_run BOOL`, `status`, `started_at`, `completed_at`
- `api/routers/playbooks.py` — `GET /playbooks` (list), `POST /playbooks/test` (dry-run against a synthetic Golden Record), `GET /playbooks/runs` (execution history)
- Unit tests: `tests/unit/test_playbook_engine.py` — trigger matching, dry-run no-ops, cooldown enforcement, partial failure handling

### Acceptance Criteria

- A Golden Record matching a playbook trigger executes its actions within 30 seconds of the record being written
- Dry-run mode executes the full evaluation and logs intended actions without calling external APIs
- Cooldown window prevents the same playbook from firing more than once per cluster per configured interval
- A failure in one action step is logged and does not block subsequent steps
- Playbook definitions can be changed in `config/playbooks.json` without restarting any service

### Dependencies

F5 complete (ad platform integration provides the action targets). F1 complete (alerting provides the Slack escalation path).

---

## F7 — Performance Feedback Loop

**Goal:** The system measures whether Golden Records led to business outcomes (CTR lift, conversion increase) and uses that signal to auto-calibrate `MPI_THRESHOLD` and source weights — closing the intelligence loop.

**Duration:** 2 weeks

### Deliverables

- `alembic/versions/008_performance_events.py` — `performance_events` table: `golden_record_id`, `platform`, `metric` (`ctr`, `conversions`, `impression_share`), `value NUMERIC`, `measured_at`, `measurement_window_hours`
- `integrations/performance_collector.py` — polls Google Ads and Meta for campaign performance metrics linked to audiences created by F5; writes to `performance_events`
- `predictive/threshold_calibrator.py` — computes precision/recall of Golden Records over a rolling 30-day window; suggests updated `MPI_THRESHOLD` and `source_weights` when statistical significance is reached (minimum 30 samples)
- `etl/dags/calibration_dag.py` — weekly DAG that runs `threshold_calibrator.py` and writes suggested config changes to a `calibration_proposals` table for human review before applying
- `api/routers/performance.py` — `GET /performance/summary` (Golden Record hit rate, avg CTR lift by cluster), `POST /performance/apply-proposal/{id}` (apply a calibration proposal)
- `dashboard/src/components/PerformancePanel.jsx` — sidebar panel showing Golden Record hit rate (% that produced measurable CTR lift), top performing clusters, and pending calibration proposals

### Acceptance Criteria

- Performance metrics are collected within 24 hours of an audience sync (F5 prerequisite)
- `threshold_calibrator.py` produces no suggestion until 30+ Golden Records have measured outcomes
- Calibration proposals require explicit human approval via `POST /performance/apply-proposal/{id}` — no auto-apply
- Golden Record "hit rate" (outcome positive / total issued) is visible in the dashboard
- The feedback loop cannot lower `MPI_THRESHOLD` below 0.5 or raise it above 0.95 regardless of calibration output (safety bounds)

### Dependencies

F5 complete (audience sync creates the measurement anchor). F2 complete (historical data needed for baseline comparison).

---

## F8 — Stream Processing Upgrade (Kafka Streams)

**Goal:** Replace the 5-minute Airflow batch enrichment with a Kafka Streams consumer for sub-30-second signal classification, closing the gap between ingestion and actionable intelligence.

**Duration:** 2–3 weeks

### Deliverables

- `streaming/classifier_stream.py` — `ClassifierStream`: Kafka Streams-style consumer using `kafka-python` + `asyncio`; consumes `raw_signals`, classifies in micro-batches of 5 (not 20 — lower latency), writes to `enriched_signals` topic and DB within 30 seconds of ingestion
- `streaming/mpi_stream.py` — `MPIStream`: maintains an in-memory rolling window of enriched signals per topic cluster; recomputes MPI on every new signal; publishes `mpi_update` events to a new Kafka topic when MPI changes by > 0.05
- `streaming/golden_record_stream.py` — `GoldenRecordStream`: listens to `mpi_update` topic; triggers Golden Record generation when MPI crosses threshold; replaces the 5-minute polling in `threshold_monitor.py`
- `config/streaming.json` — tunable parameters: micro-batch size, MPI recompute debounce (ms), rolling window size, max in-flight LLM requests
- `docker-compose.yml` — updated with `streaming-classifier`, `streaming-mpi`, `streaming-golden-record` services; Airflow DAGs kept as fallback (configurable via `ENRICHMENT_MODE=streaming|batch`)
- `alembic/versions/009_stream_offsets.py` — `kafka_stream_offsets` table for exactly-once semantics (consumer group + partition + offset)
- Integration tests: `tests/integration/test_classifier_stream.py` — end-to-end: produce to `raw_signals`, assert enriched signal in DB within 30 seconds

### Acceptance Criteria

- A raw signal produced to `raw_signals` appears as an enriched signal in the DB within 30 seconds under normal load
- MPI is recomputed within 5 seconds of a new enriched signal arriving for an active topic cluster
- `ENRICHMENT_MODE=batch` falls back to the Airflow DAG path with no code changes to the DAG
- Restarting the streaming service resumes from the last committed Kafka offset — no signal is processed twice
- LLM API rate limits (429) apply the same exponential backoff as the batch path; the consumer does not crash

### Dependencies

Sprint 3 complete (batch path validated and understood). F2 complete (historical baseline used by the MPI stream).

---

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

---

## Estado actual del proyecto

```
Sprint 1 — Infrastructure & Kafka         [x] Completado
Sprint 2 — Ingestion Layer                [x] Completado
Sprint 3 — Semantic ETL (Airflow + LLM)   [x] Completado
Sprint 4 — Predictive Processing (MPI)    [x] Completado
Sprint 5 — Backend API (FastAPI)          [x] Completado
Sprint 6 — Dashboard & End-to-End        [x] Completado
F1  — Alerting & Notifications            [x] Completado
F2  — Historical Baseline                 [x] Completado
F3  — Data Source Expansion               [x] Completado
F4  — API Security & Auth                 [x] Completado
F5  — Ad Platform Integration             [x] Completado
F6  — Automated Playbook Engine           [x] Completado
F7  — Performance Feedback Loop           [x] Completado (2026-05-02)
F8  — Stream Processing Upgrade           [x] Completado (2026-05-02)
```