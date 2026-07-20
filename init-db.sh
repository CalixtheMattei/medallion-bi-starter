#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# init-db.sh — Idempotent database + schema bootstrap.
#
# Automatically executed by Postgres on the FIRST container start
# (mounted into /docker-entrypoint-initdb.d/).
#
# IDEMPOTENCY: Safe to run multiple times.
#   - Databases: created only if they do not already exist (SELECT ... \gexec trick;
#     `CREATE DATABASE` cannot run inside a transaction, so a DO block won't work).
#   - Schemas:   use `CREATE SCHEMA IF NOT EXISTS`.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo ">>> [init-db] Creating databases (idempotent)..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
  -- Create each database only if it does not already exist.
  -- \gexec pipes the query result as a new SQL command; if the WHERE clause
  -- returns no row the command string is never emitted, so nothing is executed.
  SELECT 'CREATE DATABASE warehouse'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'warehouse')
  \gexec

  SELECT 'CREATE DATABASE dagster'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dagster')
  \gexec

  SELECT 'CREATE DATABASE metabase'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metabase')
  \gexec
EOSQL

echo ">>> [init-db] Creating schemas in warehouse (idempotent)..."

# Pre-create the two schemas used by the stack so that:
#   1. dbt seed / dbt run don't need CREATE SCHEMA privilege granted separately.
#   2. Permissions are explicit, avoiding surprises on shared Postgres instances.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "warehouse" <<-'EOSQL'
  CREATE SCHEMA IF NOT EXISTS raw;        -- EL landing zone (dbt seed / future EL tool)
  CREATE SCHEMA IF NOT EXISTS analytics;  -- dbt transformation output (staging + marts)
EOSQL

echo ">>> [init-db] Done."
echo ">>>   Databases : warehouse | dagster | metabase"
echo ">>>   Schemas   : warehouse.raw | warehouse.analytics"
