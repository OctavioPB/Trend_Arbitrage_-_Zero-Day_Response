# CLAUDE.md — Trend Arbitrage & Zero-Day Response System

## Project Overview

A real-time marketing intelligence platform that detects external demand spikes (competitors, cultural moments, social signals) and automatically prepares audience segments before trends saturate. The system captures market "noise," validates it with AI, and produces actionable data layers for marketing teams within minutes of a signal appearing.

**Core value proposition:** Be the first bidder on emerging keywords and content angles by reacting to market pressure before competitors notice it.

---

## Architecture Summary

```
[Data Sources] → Kafka (buffer) → Airflow (ETL + LLM enrichment) → Predictive Engine → Dashboard
    Reddit API
    Twitter/X API
    Web Scrapers
```

### Four Pipeline Layers

1. **Ingestion** — Kafka streams from social APIs and scrapers
2. **Semantic ETL** — Airflow DAGs + LLM classification (threat / opportunity / noise)
3. **Predictive Processing** — Market Pressure Index calculation + Golden Record generation
4. **Visualization** — Ephemeral Opportunity Heat Map (last 60 minutes, velocity-aware)

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Message broker | Apache Kafka | Decouple ingestion from processing; handle burst traffic |
| Orchestration | Apache Airflow | Schedule and monitor ETL DAGs |
| LLM classification | Anthropic Claude API (`claude-sonnet-4-20250514`) | Categorize raw signals semantically |
| Data store | PostgreSQL + Redis | Persistent records + ephemeral cache for hot signals |
| Backend API | FastAPI (Python) | Serve enriched data to the dashboard |
| Frontend | React + Recharts | Heat map and real-time trend dashboard |
| Containerization | Docker + Docker Compose | Local dev; production-ready via Compose profiles |
| Scraping | Playwright or Scrapy | Competitor site monitoring |

---

## Repository Structure

```
trend-arbitrage/
├── CLAUDE.md                   ← this file
├── docker-compose.yml
├── .env.example
│
├── ingestion/                  # Layer 1 — Kafka producers
│   ├── producers/
│   │   ├── reddit_producer.py
│   │   ├── twitter_producer.py
│   │   └── scraper_producer.py
│   ├── consumers/
│   │   └── raw_event_consumer.py
│   └── config/
│       └── kafka_config.py
│
├── etl/                        # Layer 2 — Airflow DAGs + enrichment
│   ├── dags/
│   │   ├── semantic_enrichment_dag.py
│   │   └── golden_record_dag.py
│   ├── tasks/
│   │   ├── llm_classifier.py
│   │   ├── entity_extractor.py
│   │   └── deduplicator.py
│   └── prompts/
│       └── classification_prompt.txt
│
├── predictive/                 # Layer 3 — Market Pressure Index
│   ├── mpi_calculator.py
│   ├── threshold_monitor.py
│   └── golden_record_generator.py
│
├── api/                        # FastAPI backend
│   ├── main.py
│   ├── routers/
│   │   ├── signals.py
│   │   ├── mpi.py
│   │   └── segments.py
│   └── schemas/
│       └── models.py
│
├── dashboard/                  # React frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── HeatMap.jsx
│   │   │   ├── TrendCard.jsx
│   │   │   └── MpiGauge.jsx
│   │   └── App.jsx
│   └── package.json
│
├── tests/
│   ├── unit/
│   └── integration/
│
└── docs/
    ├── architecture.md
    └── data_dictionary.md
```

---

## Environment Variables

Copy `.env.example` to `.env` and populate before running anything.

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC_RAW=raw_signals
KAFKA_TOPIC_ENRICHED=enriched_signals

# Data Sources
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=trend-arbitrage/1.0
TWITTER_BEARER_TOKEN=...

# Database
POSTGRES_DSN=postgresql://user:pass@localhost:5432/trend_arbitrage
REDIS_URL=redis://localhost:6379/0

# Pipeline
MPI_THRESHOLD=0.72          # Trigger Golden Record generation above this
SIGNAL_WINDOW_MINUTES=60    # Rolling window for heat map
LLM_MODEL=claude-sonnet-4-20250514
LLM_MAX_TOKENS=512
```

---

## Layer 1 — Ingestion (Kafka)

### Responsibilities
- Continuously poll Reddit, Twitter/X, and competitor sites
- Publish raw events to `raw_signals` Kafka topic
- Never block on downstream processing; Kafka is the safety valve

### Raw Event Schema (JSON)
```json
{
  "event_id": "uuid4",
  "source": "reddit | twitter | scraper",
  "collected_at": "ISO8601",
  "raw_text": "...",
  "url": "...",
  "author": "...",
  "engagement_score": 0.0,
  "metadata": {}
}
```

### Key Implementation Notes
- Reddit producer uses `praw` library; poll every 90 seconds per subreddit
- Twitter producer uses filtered stream endpoint (v2 API); filter by competitor handles + brand keywords
- Scraper producer runs Playwright headless; respect `robots.txt`; randomize delays 3–8 seconds
- Producers must be idempotent: include `event_id` to allow Kafka exactly-once semantics

---

## Layer 2 — Semantic ETL (Airflow + LLM)

### DAG: `semantic_enrichment_dag`
- **Schedule:** Every 5 minutes (or triggered by Kafka consumer reaching batch threshold)
- **Input:** Messages from `raw_signals` topic
- **Output:** Enriched records in PostgreSQL `enriched_signals` table + `enriched_signals` Kafka topic

### LLM Classification Task

Use the Anthropic API to classify each raw signal. Keep prompts in `etl/prompts/classification_prompt.txt` — never hardcode them in Python files.

**Classification output schema (JSON):**
```json
{
  "category": "opportunity | threat | noise",
  "confidence": 0.0,
  "topic_tags": ["keyword1", "keyword2"],
  "sentiment": "positive | negative | neutral",
  "urgency": "low | medium | high",
  "reasoning": "one-sentence explanation"
}
```

**API call pattern:**
```python
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=512,
    system=open("prompts/classification_prompt.txt").read(),
    messages=[{"role": "user", "content": raw_text}]
)
```

- Process signals in batches of 20; use `asyncio` + `anthropic.AsyncAnthropic` for parallelism
- Implement exponential backoff on API rate limit errors (429)
- Log `confidence < 0.6` cases for human review; do not discard them

### Enriched Signal Schema (PostgreSQL)
```sql
CREATE TABLE enriched_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL UNIQUE,
    source          TEXT NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    enriched_at     TIMESTAMPTZ DEFAULT NOW(),
    category        TEXT CHECK (category IN ('opportunity','threat','noise')),
    confidence      NUMERIC(4,3),
    topic_tags      TEXT[],
    sentiment       TEXT,
    urgency         TEXT,
    engagement_score NUMERIC(10,4),
    raw_text        TEXT,
    url             TEXT,
    reasoning       TEXT
);
```

---

## Layer 3 — Predictive Processing

### Market Pressure Index (MPI)

The MPI is a rolling score (0.0–1.0) per topic cluster, calculated every 5 minutes over the last `SIGNAL_WINDOW_MINUTES`.

**Formula (reference implementation):**
```
MPI = (volume_score * 0.4) + (velocity_score * 0.35) + (sentiment_score * 0.25)

where:
  volume_score   = signals_in_window / baseline_avg_signals
  velocity_score = (signals_last_15min / signals_prev_15min) - 1   [normalized 0-1]
  sentiment_score = proportion of 'positive' signals in window
```

Weights are configurable via environment or a `config/mpi_weights.json` file — do not hardcode them.

### Threshold Trigger → Golden Record

When `MPI >= MPI_THRESHOLD` for a topic cluster:
1. Query `enriched_signals` for all opportunity-category signals on that cluster in the window
2. Extract audience proxy attributes (subreddits, Twitter accounts, site sections engaged)
3. Write a `golden_records` row to PostgreSQL
4. Publish a `golden_record_ready` event to Kafka for downstream marketing tools to consume

```sql
CREATE TABLE golden_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    topic_cluster   TEXT NOT NULL,
    mpi_score       NUMERIC(4,3),
    signal_count    INT,
    audience_proxy  JSONB,   -- subreddits, handles, site sections
    recommended_action TEXT,
    expires_at      TIMESTAMPTZ  -- calculated as NOW() + signal_half_life
);
```

---

## Layer 4 — Visualization (Heat Map Dashboard)

### Requirements
- **Refresh:** WebSocket push every 60 seconds; do not poll REST
- **Heat Map axes:** X = topic cluster, Y = time bucket (last 60 min in 5-min slots)
- **Cell color:** Encodes MPI score (cool = low, hot = high); use a perceptually uniform colormap (viridis or inferno)
- **Cell size / pulse animation:** Encodes velocity (faster growth = larger pulse)
- **Sidebar:** Top 5 active Golden Records with recommended action and time-to-expiry countdown
- **No historical data on this view** — this is an operational screen, not a reporting screen

### FastAPI WebSocket endpoint
```python
@app.websocket("/ws/heatmap")
async def heatmap_ws(websocket: WebSocket):
    # Push updated MPI grid every 60s
    # Client reconnects automatically on disconnect
```

---

## Development Commands

```bash
# Start all infrastructure (Kafka, Postgres, Redis, Airflow)
docker-compose up -d

# Run ingestion producers locally
python ingestion/producers/reddit_producer.py
python ingestion/producers/twitter_producer.py

# Trigger enrichment DAG manually (Airflow CLI)
airflow dags trigger semantic_enrichment_dag

# Start FastAPI dev server
uvicorn api.main:app --reload --port 8000

# Start React dashboard
cd dashboard && npm run dev

# Run tests
pytest tests/unit/
pytest tests/integration/   # requires Docker services running
```

---

## Coding Standards

- **Python:** 3.11+, `ruff` for linting, `black` for formatting, type hints on all public functions
- **Async:** Use `asyncio` throughout; no blocking calls in the ETL hot path
- **Secrets:** Never commit `.env`; never log API keys; use `python-dotenv` locally
- **Error handling:** All Kafka producers/consumers must handle connection failures gracefully with retry logic
- **LLM calls:** Always validate JSON response structure before persisting; wrap in try/except with fallback category = `"noise"`
- **Tests:** Unit-test the MPI formula and LLM classifier in isolation using mocked API responses; integration tests use testcontainers
- **Migrations:** Use `alembic` for all PostgreSQL schema changes; never ALTER TABLE manually

---

## Key Design Constraints

1. **The system must never block ingestion.** If the LLM API is slow, Kafka absorbs the backlog. Ingestion uptime is paramount.
2. **Golden Records have a TTL.** A trend that was "hot" 4 hours ago is worthless. Calculate `expires_at` based on topic velocity decay, not a fixed offset.
3. **MPI weights must be tunable without a code deploy.** Marketing teams will want to adjust sensitivity; expose weights via a config endpoint or environment variables.
4. **The heat map is not a reporting tool.** It must not contain week-over-week comparisons or aggregate totals. Scope it strictly to the rolling window.
5. **LLM classification is advisory, not authoritative.** Always store `confidence` and `reasoning`; surface low-confidence signals for human review rather than silently dropping them.

---

## Out of Scope (v1)

- Paid ad platform integration (Google Ads, Meta Ads API) — consume the `golden_record_ready` Kafka event externally
- Historical trend analysis / BI reporting — use a separate data warehouse layer
- Multi-tenant support
- User authentication on the dashboard (internal tool assumption)

---

## Recommended Build Order

1. `docker-compose.yml` — Kafka, Postgres, Redis, Airflow containers
2. `ingestion/` — Reddit producer first (simplest auth); verify messages land in Kafka
3. `etl/tasks/llm_classifier.py` — Test classification in isolation with 20 sample signals
4. `etl/dags/semantic_enrichment_dag.py` — Wire classifier into Airflow
5. `predictive/mpi_calculator.py` — Unit-test formula with synthetic data
6. `api/` — FastAPI with REST endpoints, then add WebSocket
7. `dashboard/` — Static heat map first, then add WebSocket live updates
8. `tests/integration/` — End-to-end pipeline test with a seeded Kafka topic
