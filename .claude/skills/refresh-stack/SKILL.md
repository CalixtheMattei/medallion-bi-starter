---
name: refresh-stack
description: Run dbt for new or modified models — checks raw tables exist, validates column types, runs dbt, and syncs Metabase. Use after adding a new staging model, mart, or source.
---

# refresh-stack

Run the pre-flight checks, then build the dbt models and sync Metabase.

## Stack context

- **dbt project**: `dbt/` (mounted into Docker as `/dbt`)
- **Docker service**: `dagster_user_code`
- **Metabase URL**: `http://localhost:3000`
- **Credentials**: `.env` — `METABASE_USER` / `METABASE_PASSWORD`

---

## Step 1 — Check raw tables exist

For each source table referenced by the models being built, verify it landed in `raw.*`:

```bash
docker compose exec -T postgres psql -U postgres -d warehouse -c "\dt raw.<source>_<table_name>"
```

If a table is **missing**: it either hasn't been loaded by Dagster yet, or it's in that source's `SKIP_TABLES` block (check the relevant `dagster/project/assets_*.py`). Tell the user which, and do not proceed until the source table is present.

## Step 2 — Validate column types

For each new or modified staging model, check the actual PostgreSQL column types against what the model expects:

```bash
docker compose exec -T postgres psql -U postgres -d warehouse -c "
  SELECT column_name, data_type
  FROM information_schema.columns
  WHERE table_schema = 'raw' AND table_name = '<source>_<table>'
  ORDER BY ordinal_position;"
```

**Key type rules for this stack:**

| Source type | Expected PostgreSQL type | dbt comparison |
|---|---|---|
| MySQL `tinyint(1)` / bit flags | Usually lands as `text` (`'0'`/`'1'`) via pandas inference | Compare with `= '1'`, not `= 1` |
| MySQL `int`, `bigint` | `bigint` | Compare with `= 1` (integer) |
| MySQL `datetime`/`timestamp` | `text` | Cast with `::timestamp` |
| API string properties (e.g. HubSpot) | `text` | Cast explicitly (`::numeric`, `::date`) — never assume type |

If the staging model uses `= 1` but the column is `text`, fix the comparison to `= '1'`. If it uses `= '1'` but the column is `bigint`, fix to `= 1`.

To spot-check actual stored values:
```bash
docker compose exec -T postgres psql -U postgres -d warehouse \
  -c "SELECT pg_typeof(<col>), <col> FROM raw.<source>_<table> LIMIT 3;"
```

## Step 3 — Run dbt

```bash
docker compose run --rm --no-deps --entrypoint dbt dagster_user_code run \
  --select <models> \
  --project-dir /dbt \
  --profiles-dir /dbt
```

Interpret the output:
- `CREATE VIEW` → staging/intermediate model created
- `SELECT N` → mart built with N rows (report this to the user)
- `SKIP` on `hubspot.*` models with no error → expected when `HUBSPOT_ACCESS_TOKEN` is unset, not a failure
- `ERROR` → read the full message; common causes are type mismatches (Step 2) or missing source tables (Step 1)

## Step 4 — Sync Metabase

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/session \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$(grep METABASE_USER .env | cut -d= -f2)\",\"password\":\"$(grep METABASE_PASSWORD .env | cut -d= -f2)\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

Find the warehouse database ID (usually `2`, but confirm):
```bash
curl -s -H "X-Metabase-Session: $TOKEN" http://localhost:3000/api/database | \
  python3 -c "import sys,json; [print(d['id'], d['name']) for d in json.load(sys.stdin).get('data',[])]"
```

Sync and confirm the new table is visible:
```bash
curl -s -X POST "http://localhost:3000/api/database/<DB_ID>/sync_schema" -H "X-Metabase-Session: $TOKEN"
sleep 5
curl -s -H "X-Metabase-Session: $TOKEN" "http://localhost:3000/api/database/<DB_ID>/metadata" | \
  python3 -c "import sys,json; [print(t['id'], t['name']) for t in json.load(sys.stdin).get('tables',[]) if 'mart' in t['name']]"
```

## Step 5 — Report

- Pre-flight: raw tables present / missing
- Type checks: any issues found and fixed
- dbt: models built, row counts, any errors or expected skips
- Metabase: new table ID(s) now visible
- Suggested next step: use `create-dashboard` to build the dashboard
