#!/bin/bash
# Creates the Airflow metadata database on first PostgreSQL startup.
# Runs automatically from /docker-entrypoint-initdb.d/ — do not call manually.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER airflow WITH PASSWORD 'airflow';
    CREATE DATABASE airflow;
    GRANT ALL PRIVILEGES ON DATABASE airflow TO airflow;
EOSQL

# PG15+ removed implicit CREATE on public schema — grant it explicitly.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "airflow" <<-EOSQL
    GRANT ALL ON SCHEMA public TO airflow;
    ALTER SCHEMA public OWNER TO airflow;
EOSQL
