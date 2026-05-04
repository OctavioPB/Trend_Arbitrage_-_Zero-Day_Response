# Trend Arbitrage & Zero-Day Response

Real-time marketing intelligence platform that detects external demand spikes — competitor moves, cultural moments, social signals — and automatically prepares audience segments before trends saturate.

**Core value proposition:** be the first bidder on emerging keywords and content angles by reacting to market pressure minutes after a signal appears, not hours.

---

## Table of Contents

- [Architecture](#architecture)
- [Pipeline Layers](#pipeline-layers)
- [Tech Stack](#tech-stack)
- [Setup](#setup)
- [Service URLs](#service-urls)
- [Project Structure](#project-structure)
- [Operating Modes](#operating-modes)
- [Configuration Without Code Deploy](#configuration-without-code-deploy)
- [Database Migrations](#database-migrations)
- [Running Tests](#running-tests)
- [Engineering Decisions](#engineering-decisions)

---

## Architecture

```
Data Sources
  Reddit · Twitter/X · LinkedIn · News APIs · RSS · Competitor scrapers
        │
        ▼
  Kafka (raw_signals)          ← ingestion safety valve; absorbs burst traffic
        │
        ├─── Batch path (ENRICHMENT_MODE=batch) ──────────────────────────────┐
        │    Airflow DAG (5-min schedule)                                      │
        │    LLM classification → enriched_signals table                      │
        │                                                                      │
        └─── Streaming path (ENRICHMENT_MODE=streaming) ─────────────────────┤
             ClassifierStream  → enriched_signals topic + DB (< 30 s)         │
             MPIStream         → mpi_update topic (in-memory rolling window)  │
             GoldenRecordStream→ golden_record_ready topic                     │
                                                                               ▼
                                                             Predictive Engine
                                                               MPI (0–1 per cluster)
                                                               Golden Records
                                                                      │
                                                                      ▼
                                                         FastAPI + WebSocket
                                                         React Heat Map Dashboard
                                                         Ad Platform Sync (Google / Meta)
                                                         Performance Feedback Loop
```

---

## Pipeline Layers

### Layer 1 — Ingestion (Kafka)

Six producers publish raw events to the `raw_signals` Kafka topic:

| Producer | Source | Notes |
|---|---|---|
| `reddit_producer.py` | Reddit API (praw) | Polls subreddits every 90 s |
| `twitter_producer.py` | Twitter v2 filtered stream | Tracks competitor handles + brand terms |
| `linkedin_producer.py` | LinkedIn via RapidAPI | Company posts every 10 min |
| `news_producer.py` | NewsAPI + GDELT | Keyword search every 5 min |
| `rss_producer.py` | RSS/Atom feeds | Configurable feed list in `config/rss_feeds.json` |
| `scraper_producer.py` | Playwright headless | Respects robots.txt; randomised delays 3–8 s |

Raw event schema:
```json
{
  "event_id": "uuid4",
  "source": "reddit | twitter | linkedin | news | rss | scraper",
  "collected_at": "ISO8601",
  "raw_text": "...",
  "url": "...",
  "author": "...",
  "engagement_score": 0.0,
  "metadata": {}
}
```

### Layer 2 — Semantic ETL (Airflow + LLM)

Airflow DAG `semantic_enrichment_dag` (5-min schedule) or `ClassifierStream` (streaming mode) classifies raw signals using Claude:

```json
{
  "category": "opportunity | threat | noise",
  "confidence": 0.87,
  "topic_tags": ["ai-chips", "gpu-shortage"],
  "sentiment": "positive | negative | neutral",
  "urgency": "low | medium | high",
  "reasoning": "one-sentence explanation"
}
```

- Processes signals in async micro-batches; exponential backoff on 429 errors
- Responses with `confidence < 0.6` are stored for human review, not discarded
- Invalid LLM responses fall back to `category="noise"` — never crash the pipeline

### Layer 3 — Predictive Processing

**Market Pressure Index (MPI):**

```
MPI = (volume_score × 0.40) + (velocity_score × 0.35) + (sentiment_score × 0.25)

volume_score    = Σ source_weight[s] / baseline_avg_signals   [0–1]
velocity_score  = (signals_last_15min / signals_prev_15min) - 1 [0–1]
sentiment_score = proportion of positive signals in window      [0–1]
```

When `MPI ≥ MPI_THRESHOLD (default 0.72)` for a topic cluster, a **Golden Record** is generated — a structured audience brief with proxy attributes, recommended action, and TTL.

### Layer 4 — Visualization & Integrations

- **React dashboard** — heat map (X = cluster, Y = 5-min time bucket, colour = MPI); WebSocket push every 60 s
- **Ad platform sync** — Google Ads custom audiences + Meta custom audiences created automatically on Golden Record trigger (F5)
- **Automated playbooks** — configurable action chains (bid adjustment, content brief webhook, Slack alert) per topic cluster (F6)
- **Performance feedback loop** — CTR/conversions collected 24 h after audience sync; calibration proposals generated weekly; human-approved threshold and weight updates (F7)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Message broker | Apache Kafka 7.5 (Confluent) + Zookeeper |
| Orchestration | Apache Airflow 2.8.4 |
| LLM classification | Anthropic Claude (`claude-sonnet-4-20250514`) |
| Data store | PostgreSQL 16 + Redis 7 |
| Backend API | FastAPI + Uvicorn |
| Frontend | React + Recharts |
| Streaming | kafka-python + asyncio (ClassifierStream / MPIStream / GoldenRecordStream) |
| Containerisation | Docker Compose |
| Migrations | Alembic |
| Auth | JWT (python-jose) + OAuth2 password grant |
| Ad platforms | Google Ads API (GAQL) + Meta Graph API |

---

## Setup

### Prerequisites

- Docker Desktop ≥ 4.x with Docker Compose v2
- Python 3.11+

### Quickstart

```powershell
# 1. Clone and configure
git clone <repo-url>
cd trend-arbitrage
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY

# 2. Start infrastructure (Kafka, Postgres, Redis, Airflow)
docker-compose up -d

# 3. Initialize the Airflow metadata database (run once after first `up`)
#    airflow-init can fail silently on first boot due to a network race condition;
#    running it explicitly guarantees the DB is migrated before the webserver starts.
docker-compose run --rm airflow-init

# 4. Apply project DB migrations (trend_arbitrage schema)
pip install alembic psycopg2-binary python-dotenv
$env:POSTGRES_DSN="postgresql://trend:trend@localhost:5433/trend_arbitrage"
alembic upgrade head

# 5. Verify services
docker-compose ps                        # all containers should be healthy
curl http://localhost:8080/health        # Airflow webserver → {"status":"healthy"}
```

> **Port offsets:** this project uses non-default host ports to coexist with other
> Docker projects. PostgreSQL is exposed on **5433** (not 5432) and Redis on **6380**
> (not 6379). Internal Docker networking still uses the standard ports — only host
> access differs.

### Activate streaming mode (optional, recommended for sub-30 s latency)

```bash
# In .env
ENRICHMENT_MODE=streaming

# Build and start streaming services alongside the base stack
docker-compose --profile streaming up -d

# Streaming services started:
#   trend_streaming_classifier    — raw_signals → enriched_signals (< 30 s)
#   trend_streaming_mpi           — enriched_signals → mpi_update (in-memory)
#   trend_streaming_golden_record — mpi_update → golden_record_ready
```

### Start the API and dashboard (development)

```powershell
# ── API ──────────────────────────────────────────────────────────────────────
pip install -r requirements.txt

# Load .env before starting uvicorn so API_ADMIN_PASSWORD and other vars are set.
# PowerShell one-liner — run from the repo root:
Get-Content .env | Where-Object { $_ -match '^\w' } | ForEach-Object { $k,$v = $_ -split '=',2; [System.Environment]::SetEnvironmentVariable($k, $v) }
uvicorn api.main:app --reload --port 8000

# ── Dashboard ─────────────────────────────────────────────────────────────────
# Use 'node ... vite.js' directly — npm/npx both spawn cmd.exe internally,
# which interprets the '&' in the repo folder name as a command separator
# and truncates the module path.
cd dashboard
npm install
node node_modules/vite/bin/vite.js
# → http://localhost:3000
```

> **Login credentials:** use the values of `API_ADMIN_USER` and `API_ADMIN_PASSWORD`
> from your `.env` file. The API returns `422` if `API_ADMIN_PASSWORD` is not set —
> confirm the env-loading step ran before starting uvicorn.

---

## Service URLs

| Service | URL | Credentials |
|---|---|---|
| Airflow UI | http://localhost:8080 | admin / admin |
| FastAPI docs | http://localhost:8000/docs | — (JWT required for protected routes) |
| React dashboard | http://localhost:3000 | API_ADMIN_USER / API_ADMIN_PASSWORD (from .env) |
| PostgreSQL | localhost:**5433** | trend / trend · db: trend_arbitrage |
| Kafka | localhost:9092 | — |
| Redis | localhost:**6380** | — |

### API authentication

```bash
# Get a JWT token
curl -X POST http://localhost:8000/auth/token \
  -d "username=admin&password=<API_ADMIN_PASSWORD>" \
  -H "Content-Type: application/x-www-form-urlencoded"

# Use the token
curl http://localhost:8000/mpi/clusters \
  -H "Authorization: Bearer <token>"
```

---

## Project Structure

```
ingestion/
  producers/          Six Kafka producers (Reddit, Twitter, LinkedIn, News, RSS, scraper)
  consumers/          Raw event consumer stub
  config/             kafka_config.py — bootstrap servers, topic names, retry helpers

etl/
  dags/               Airflow DAGs: semantic_enrichment, golden_record, calibration
  tasks/              llm_classifier.py, db_writer.py, entity_extractor.py, deduplicator.py
  prompts/            classification_prompt.txt — never hardcoded in Python

streaming/
  classifier_stream.py   Kafka Streams-style micro-batch LLM classifier (< 30 s)
  mpi_stream.py          In-memory rolling window MPI recomputation
  golden_record_stream.py  MPI threshold trigger → Golden Record generation
  _offsets.py            kafka_stream_offsets DB helper (exactly-once)

predictive/
  mpi_calculator.py      MPI formula with configurable weights
  golden_record_generator.py
  threshold_monitor.py   Batch-path polling fallback
  threshold_calibrator.py  Precision/recall calibration → proposals
  mpi_archiver.py        Historical baseline queries

integrations/
  audience_mapper.py     Topic cluster → audience segment mapping
  google_ads.py          Google Ads API (custom audiences, bid adjustments)
  meta_ads.py            Meta Graph API (custom audiences)
  performance_collector.py  CTR/conversions collection 24 h post-sync

alerting/
  notifier.py            Slack webhook, generic webhook, SMTP email alerts
  config.py              Alert rule loading from alert_rules DB table

playbooks/              (loaded from config/playbooks.json at runtime)

api/
  main.py               FastAPI app, router registration
  routers/              signals, mpi, segments, alerts, auth, history,
                        performance, playbooks

dashboard/
  src/components/       HeatMap, TrendCard, MpiGauge, ActiveSegments,
                        PerformancePanel, PlaybookPanel

config/
  mpi_weights.json      MPI component weights (no restart needed)
  source_weights.json   Per-source signal multipliers (no restart needed)
  streaming.json        Streaming pipeline parameters (restart required)
  audience_mapping.json  Cluster → ad audience attributes
  playbooks.json        Playbook definitions and action chains
  rss_feeds.json        RSS/Atom feed list

alembic/versions/
  001 — initial schema (enriched_signals, golden_records)
  002 — alert_rules
  003 — mpi_history
  004 — source_weights_log
  005 — api_keys
  006 — audience_sync_log
  007 — playbook_runs
  008 — performance_events, calibration_proposals
  009 — kafka_stream_offsets

tests/
  unit/                 No Docker required
  integration/          Require docker-compose up -d (marked @pytest.mark.integration)
```

---

## Operating Modes

### Batch mode (default)

Airflow DAG runs every 5 minutes, polls Kafka, classifies signals in batches of 20, writes to DB. Latency: 1–10 minutes from ingestion to Golden Record.

```bash
ENRICHMENT_MODE=batch   # default — no streaming containers needed
```

### Streaming mode

Three long-running services replace the Airflow ETL hot path. Latency: < 30 seconds end-to-end.

```bash
ENRICHMENT_MODE=streaming
docker-compose --profile streaming up -d
```

The Airflow DAGs remain deployed and functional as a fallback. Switching back to batch mode is `ENRICHMENT_MODE=batch` + stopping the streaming containers — no schema changes.

**Exactly-once semantics in streaming mode:**

- `enable_auto_commit=False` — Kafka offsets committed manually after DB write succeeds
- `kafka_stream_offsets` table stores committed position per (consumer_group, topic, partition)
- On restart, consumers seek to the stored offset and resume without reprocessing
- `enriched_signals` inserts use `ON CONFLICT (event_id) DO NOTHING` — safe to replay

---

## Configuration Without Code Deploy

These files are reloaded at runtime — edit and save; no restart required unless noted.

| File | Controls | Restart? |
|---|---|---|
| `config/mpi_weights.json` | Volume / velocity / sentiment weights in MPI formula | No |
| `config/source_weights.json` | Per-source signal multipliers (reddit, twitter, news…) | No |
| `config/audience_mapping.json` | Cluster → ad audience targeting attributes | No |
| `config/playbooks.json` | Playbook definitions, action chains, dry-run flag | No |
| `config/rss_feeds.json` | RSS/Atom feeds polled by the RSS producer | Producer restart |
| `config/streaming.json` | Micro-batch size, debounce, rolling window, cooldown | Streaming restart |
| `.env` (`MPI_THRESHOLD`) | Golden Record trigger threshold | Process restart |
| `.env` (`ENRICHMENT_MODE`) | Switch batch ↔ streaming | Full service restart |

**Calibration proposals** (F7) can auto-update `source_weights.json` via `POST /performance/apply-proposal/{id}` — write is atomic (temp file + rename). `MPI_THRESHOLD` changes are returned as a note in the API response for manual `.env` update.

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "add foo column"

# Roll back one step
alembic downgrade -1

# Check current revision
alembic current
```

---

## Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Unit tests only (no Docker required)
pytest tests/unit/ -v

# Integration tests (requires docker-compose up -d + alembic upgrade head)
pytest tests/integration/ -v -m integration

# Specific module
pytest tests/unit/test_mpi_calculator.py -v
pytest tests/integration/test_classifier_stream.py -v -m integration

# Lint + format
ruff check .
black --check .
```

---

## Engineering Decisions

### 1. Kafka as the ingestion safety valve

All six producers write to Kafka regardless of downstream throughput. If the LLM API slows down or Airflow is restarting, producers keep running and messages accumulate in the topic. This means ingestion uptime is decoupled from processing uptime — the most important property for a real-time intelligence system.

Kafka is also the handoff point between batch and streaming paths: both modes consume `raw_signals`; the switchover requires no producer changes.

### 2. Dual-mode pipeline: batch and streaming

The Airflow batch path was the baseline v1 implementation. The streaming path (F8) was added as an opt-in upgrade rather than a replacement. Rationale:

- The batch path is simpler to operate and debug; streaming adds operational complexity
- Teams can validate the streaming path in a staging environment before switching production
- `ENRICHMENT_MODE=batch` is the safe default; streaming is explicitly activated
- Rolling back streaming requires one env var change and a container stop — no schema rollback

### 3. In-memory rolling window for MPI (no DB reads on the hot path)

`MPIStream` maintains a `deque`-per-cluster in memory. Each new enriched signal is appended; signals older than `rolling_window_minutes` are evicted on access. MPI is recomputed from the in-memory window — zero DB reads during steady-state processing.

The baseline average (needed for volume normalisation) is cached with a 5-minute TTL and fetched from `mpi_history` on miss. This means MPI computation latency is bounded by LLM latency, not DB latency.

Trade-off: the window is rebuilt from the Kafka consumer's stored offset on restart, not from the DB. If a large backlog exists, the first few minutes after restart may have incomplete windows — acceptable given the 60-minute window and typical restart durations.

### 4. MPI change threshold and debounce

`MPIStream` only publishes an `mpi_update` event when the new MPI differs from the last published value by ≥ 0.05 (`mpi_change_threshold`). Additionally, a per-cluster debounce of 500 ms prevents thrashing during signal bursts. Without these two controls, a cluster receiving 100 signals per second would generate 100 MPI computations and 100 downstream events per second.

Both values are tunable in `config/streaming.json` without a code change (streaming restart required).

### 5. LLM classification is advisory, not authoritative

Every classification result stores `confidence` and `reasoning`. Signals with `confidence < 0.6` are flagged for human review but not dropped — the system never silently discards data. Invalid JSON from the LLM falls back to `category="noise"` so the pipeline continues. This design means the LLM is a signal enhancer, not a gatekeeper.

### 6. Golden Record cooldown

`GoldenRecordStream` tracks the last generation time per cluster in memory. If a cluster's MPI oscillates around the threshold (0.72 → 0.68 → 0.74 within 2 minutes), only one Golden Record is generated. Cooldown default is 5 minutes, configurable in `streaming.json`. The cooldown resets on restart — intentional, so the first crossing after a restart always triggers a record.

### 7. Source weight multipliers reloaded every call

`load_source_weights()` reads `config/source_weights.json` on every MPI computation. This means a weight change to "news" sources (currently 1.2) takes effect on the next signal without a restart. The file is small (~200 bytes) and the stat/read cost is negligible compared to the LLM API calls dominating latency.

The performance feedback loop (F7) can write updated weights atomically via `tmp_file.replace(target)` — no partial-write window where the calculator would read a corrupted file.

### 8. Calibration proposals require human approval

`ThresholdCalibrator` writes suggestions to `calibration_proposals` with `status="pending"`. Weights can be applied via `POST /performance/apply-proposal/{id}`. The `MPI_THRESHOLD` is returned as a note — it requires a manual `.env` update and process restart. This is intentional: automatic threshold changes to a live marketing system would be high-risk, especially early in the feedback loop's life when sample sizes are small (minimum 30 Golden Records required before any proposal is generated).

### 9. Exactly-once semantics without Kafka transactions

Kafka transactions add significant complexity and require a specific broker configuration. Instead the system achieves the same effect with three complementary mechanisms:

1. **Manual offset commits** — Kafka offset committed only after the DB write succeeds. A crash between write and commit causes re-processing on restart.
2. **Idempotent DB inserts** — `INSERT INTO enriched_signals … ON CONFLICT (event_id) DO NOTHING`. Re-processing a batch is a no-op.
3. **Secondary offset store** — `kafka_stream_offsets` table stores the committed position. If the Kafka consumer group state is lost (broker restart, group ID change), the consumer seeks to the DB-stored position.

### 10. JWT auth with rate limiting

The FastAPI API requires a JWT bearer token for all non-public routes. Tokens are issued via OAuth2 password grant (`POST /auth/token`). Rate limits (60 req/min read, 20 req/min write) are applied per IP at the middleware layer — not per user, which is acceptable for an internal tool assumption.

API keys for machine-to-machine access (e.g., ad platform webhooks) are stored in the `api_keys` table and validated separately from user JWTs.
