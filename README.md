# Trend Arbitrage & Zero-Day Response

Real-time marketing intelligence platform that detects demand spikes and prepares audience segments before trends saturate.

## Prerequisites

- Docker Desktop ≥ 4.x with Docker Compose v2
- Python 3.11+

## Local dev quickstart

```bash
# 1. Clone and configure
git clone <repo-url>
cd trend-arbitrage
cp .env.example .env
# Edit .env and fill in ANTHROPIC_API_KEY and API credentials

# 2. Start all infrastructure
docker-compose up -d

# 3. Wait ~60s for Airflow to initialize, then run DB migrations
pip install alembic psycopg2-binary python-dotenv
alembic upgrade head

# 4. Verify everything is up
docker-compose ps                          # all services should be healthy
kafka-topics.sh --bootstrap-server localhost:9092 --list   # raw_signals, enriched_signals, golden_record_ready
redis-cli ping                             # PONG
curl http://localhost:8080/health          # Airflow webserver
```

## Service URLs

| Service | URL | Credentials |
|---|---|---|
| Airflow UI | http://localhost:8080 | admin / admin |
| PostgreSQL | localhost:5432 | trend / trend (db: trend_arbitrage) |
| Kafka | localhost:9092 | — |
| Redis | localhost:6379 | — |

## Running migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Generate a new migration after schema changes
alembic revision --autogenerate -m "description of change"

# Roll back one step
alembic downgrade -1
```

## Project structure

```
ingestion/      Kafka producers (Reddit, Twitter, scraper) — Sprint 2
etl/            Airflow DAGs + LLM classification tasks — Sprint 3
predictive/     MPI calculator + Golden Record generator — Sprint 4
api/            FastAPI backend + WebSocket endpoint — Sprint 5
dashboard/      React heat map — Sprint 6
config/         Tunable weights and thresholds (no code deploy needed)
alembic/        Database migrations
tests/          Unit and integration tests
docs/           Architecture and data dictionary
```

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Lint
ruff check .

# Format
black .

# Tests (unit only — no Docker required)
pytest tests/unit/ -v

# Tests (integration — requires docker-compose up -d)
pytest tests/integration/ -v
```
