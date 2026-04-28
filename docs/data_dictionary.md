# Data Dictionary

## enriched_signals

| Column | Type | Nullable | Description |
|---|---|---|---|
| id | UUID | NO | Primary key, auto-generated |
| event_id | UUID | NO | Unique ID from the raw event; prevents duplicate processing |
| source | TEXT | NO | `reddit`, `twitter`, or `scraper` |
| collected_at | TIMESTAMPTZ | NO | When the raw event was captured by the producer |
| enriched_at | TIMESTAMPTZ | YES | When LLM classification completed; defaults to NOW() |
| category | TEXT | YES | `opportunity`, `threat`, or `noise` |
| confidence | NUMERIC(4,3) | YES | LLM confidence score 0.000–1.000 |
| topic_tags | TEXT[] | YES | Array of keyword/topic labels extracted by the classifier |
| sentiment | TEXT | YES | `positive`, `negative`, or `neutral` |
| urgency | TEXT | YES | `low`, `medium`, or `high` |
| engagement_score | NUMERIC(10,4) | YES | Platform-native engagement signal (upvotes, retweets, etc.) |
| raw_text | TEXT | YES | Original text from the source |
| url | TEXT | YES | Source URL |
| reasoning | TEXT | YES | One-sentence LLM explanation of the classification |

## golden_records

| Column | Type | Nullable | Description |
|---|---|---|---|
| id | UUID | NO | Primary key, auto-generated |
| created_at | TIMESTAMPTZ | YES | When this record was generated; defaults to NOW() |
| topic_cluster | TEXT | NO | Topic label that triggered the MPI threshold |
| mpi_score | NUMERIC(4,3) | YES | MPI score at time of generation (0.000–1.000) |
| signal_count | INTEGER | YES | Number of enriched signals in the window for this cluster |
| audience_proxy | JSONB | YES | Inferred audience attributes: subreddits, handles, site sections |
| recommended_action | TEXT | YES | Suggested marketing action |
| expires_at | TIMESTAMPTZ | YES | When this opportunity is considered stale (velocity-decay based) |
