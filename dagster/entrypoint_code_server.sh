#!/bin/bash
# Entrypoint for the dagster_user_code service.
# 1. Generates the dbt manifest (required by @dbt_assets decorator).
# 2. Starts the Dagster gRPC code server on port 4000.
set -e

echo ">>> Generating dbt manifest (dbt parse)..."
dbt parse --project-dir /dbt --profiles-dir /dbt

echo ">>> Starting Dagster code server on port 4000..."
exec dagster code-server start -h 0.0.0.0 -p 4000 -m project
