---
name: setup
description: Guided first launch of the medallion BI starter stack — build, materialize the demo assets, and verify a mart has rows. Use when a user wants to run this repo for the first time.
---

# setup

Get the stack running end-to-end from a fresh clone, using the bundled demo data — no external credentials required.

## Stack context

See [AGENTS.md](../../../AGENTS.md) for full architecture and conventions. Short version: Dagster extracts MySQL → Postgres `raw.*`, dbt transforms `raw.*` → `analytics.*`, Metabase reads `analytics.*`.

## Steps

### 1 — Environment file

```bash
test -f .env || cp .env.example .env
```

Tell the user: the defaults work as-is for the demo. If they want to point at a real MySQL source, they can edit `.env` now or later — nothing below depends on it.

### 2 — Build and start

```bash
docker compose up -d --build
```

This starts: `mysql-demo` (seeded automatically from `demo-source/seed.sql` on first boot), `postgres` (three databases via `init-db.sh`), `dagster_user_code`, `dagster_webserver`, `dagster_daemon`, `metabase`.

### 3 — Wait for health

```bash
docker compose ps
```

Confirm `postgres` and `mysql-demo` show `(healthy)`. Dagit (port 3001) is typically ready in ~20s; Metabase (port 3000) takes ~60–90s. If a container is restarting, check its logs: `docker compose logs <service> --tail 50`.

### 4 — Materialize the raw extract

There is no dependency edge wired up between `mysql_raw_load` and the dbt assets (dagster-dbt can't map four distinct dbt source tables onto one upstream Dagster asset), so **never use Dagit's "Materialize all" button on the asset graph** — it runs everything at once with no ordering guarantee, and the dbt build will fail looking for `raw.*` tables that don't exist yet.

```bash
docker compose exec -T dagster_user_code dagster job execute -j daily_mysql_ingest_job -m project
```

Verify raw tables landed before continuing:
```bash
docker compose exec -T postgres psql -U postgres -d warehouse -c "\dt raw.*"
```
Expect `shop_customers`, `shop_products`, `shop_orders`, `shop_order_items`.

If the command isn't available in the image, tell the user to open Dagit → http://localhost:3001 → Jobs → `daily_mysql_ingest_job` → Launch instead.

### 5 — Metabase setup (headless, no browser needed) — do this *before* the dbt job

```bash
python3 scripts/bootstrap_metabase.py
```

This completes Metabase's first-run setup wizard using `METABASE_USER`/`METABASE_PASSWORD` from `.env`, and connects the `warehouse` Postgres database (schema `analytics`) using `POSTGRES_USER`/`POSTGRES_PASSWORD` — all via Metabase's API, no clicking required. It's idempotent: safe to re-run against an already-provisioned instance (it just confirms things are already in place).

**This has to happen before step 6, not after** — `dbt-metabase` (which the dbt job calls at the end of its build) hard-fails the entire dbt job if Metabase doesn't already have a database named `warehouse` registered. It doesn't matter that Metabase's copy of the schema is stale at this point (the `analytics` tables don't exist yet) — `dbt-metabase` triggers its own resync and only *warns* about fields it can't find yet; it only raises if the `warehouse` database entry is missing entirely. Verified by hand: running the dbt job before this step fails outright with `Database not found: warehouse`; running it after succeeds cleanly, syncing every field description in the same pass.

It's also self-healing — Metabase's setup endpoint enforces a stricter password check than you'd expect (it once rejected the shipped `.env.example` placeholder outright as "too common"). If `METABASE_PASSWORD` gets rejected, the script generates a new one, completes setup with it, and rewrites `METABASE_PASSWORD` in `.env` — then tells you to restart the dagster containers so they pick up the new value:
```bash
docker compose up -d dagster_user_code dagster_webserver dagster_daemon
```

If Metabase was already set up by hand with different credentials than what's in `.env`, the script will say so rather than guessing — update `.env` to match, or reset just this repo's `metabase` Postgres database if you want a clean slate (see the script's error message for the exact command; it only ever touches this repo's own Postgres container, never a volume/database from another project).

### 6 — Build the dbt models

```bash
docker compose exec -T dagster_user_code dagster job execute -j daily_dbt_job -m project
```

Expect `CREATE VIEW` for staging/intermediate models, `SELECT N` for marts, and a final "Metabase field descriptions synced successfully" line — that sync only fires when dbt runs through this job/the `dbt_project_assets` Dagster asset, not via a bare `dbt build` CLI invocation, so don't substitute one for the other. If it fails with `Database not found: warehouse`, step 5 didn't complete — run it first.

If the command isn't available in the image, tell the user to open Dagit → http://localhost:3001 → Jobs → `daily_dbt_job` → Launch instead.

### 7 — Verify a mart has rows

```bash
docker compose exec -T postgres psql -U postgres -d warehouse \
  -c "SELECT activity_status, count(*) FROM analytics.mart_customer_activity GROUP BY 1;"
```

You should see a handful of customers across `active` / `slowing` / `dormant` / `never_ordered`. If the table doesn't exist or is empty, stop and debug.

### 8 — Bootstrap the welcome dashboard (optional, recommended)

```bash
python3 scripts/bootstrap_demo_dashboard.py
```

This builds a small "Welcome" dashboard from the two demo marts — three real charts plus a friendly intro card — so the user's first view of Metabase is a working example instead of an empty instance. It's idempotent and safe to re-run. Report the dashboard URL it prints.

## Report to the user

- Which services are healthy
- Raw tables confirmed present
- dbt build result (models built, any errors)
- Mart row counts by activity_status
- Welcome dashboard URL, if bootstrapped
- Next step: open Metabase, or hand off to the `create-dashboard` skill to build further dashboards
