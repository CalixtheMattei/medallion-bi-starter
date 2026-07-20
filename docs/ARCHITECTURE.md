# Architecture Guide

> **Who this is for:** anyone standing up or extending this stack — from "what is this" to "how do I add a source."

---

## Part 1 — What this is and why

Most teams that need self-serve analytics end up with one of two problems: analysts querying production databases directly (slow, risky, undocumented), or a BI tool pointed at a warehouse nobody governs, where every dashboard reinvents its own definition of "active customer."

This stack is a small, complete answer to that: a source database gets extracted on a schedule into a warehouse, transformed through explicit layers with enforced conventions, and exposed to a BI tool that shows business users documentation instead of raw column names.

It's built to be **read and run**, not just read. `docker compose up` gives you the whole pipeline against a synthetic e-commerce dataset with no external credentials. From there, pointing it at a real source is a `.env` change plus a new set of dbt models — the machinery doesn't change.

## Part 2 — The four tools, one job each

```
[Source: MySQL (demo) + optional HubSpot API]
          │
          │  Step 1: EXTRACT
          ▼
     DAGSTER
     Connects to the source, reads all relevant tables/objects,
     writes them to Postgres. Nothing is transformed — this is a copy.
          │
          ▼
[Postgres — raw.* schema]        ← Bronze: safe copy of the source
          │
          │  Step 2: TRANSFORM
          ▼
     dbt
     Reads the raw copy, renames columns, casts types,
     derives fields, joins tables, pre-computes business metrics.
     Writes results back into the same Postgres database.
          │
          ▼
[Postgres — analytics.* schema]  ← Silver + Gold: clean, business-ready
          │
          │  Step 3: VISUALIZE
          ▼
     METABASE
     Connects to Postgres, queries the Gold tables,
     renders charts and dashboards.
```

> **Key insight:** Metabase doesn't store data, and dbt doesn't move data to a new system. Everything lives in one Postgres database (`warehouse`). The tools just read and write it at different stages.

## Part 3 — Each tool in detail

### 3.1 Dagster — the extractor

A Python orchestrator: runs jobs, tracks success/failure, stores logs, and gives you a web UI (Dagit) to trigger and monitor runs.

**What it does here:** connects to the source MySQL (read-only), discovers tables, skips anything in the `SKIP_TABLES` blocklist, and copies the rest to Postgres in 5,000-row chunks (keeps memory flat regardless of table size).

| Term | Meaning |
|---|---|
| **Asset** | A named piece of data Dagster manages. `mysql_raw_load` *produces* the raw tables. |
| **Materialization** | Running an asset to (re)produce its output — click "Materialize" in Dagit. |
| **Job** | A named group of assets that runs together (e.g. `daily_full_pipeline_job`). |
| **Schedule** | A cron trigger for a job (e.g. `daily_mysql_3am`, 03:00 UTC). |

Two extract-load assets exist:
- `mysql_raw_load` — the database-source pattern ([dagster/project/assets_mysql_source.py](../dagster/project/assets_mysql_source.py))
- `hubspot_raw_load` — the API-source pattern, optional, self-skips if `HUBSPOT_ACCESS_TOKEN` is unset ([dagster/project/assets_hubspot.py](../dagster/project/assets_hubspot.py))

Both are **resumable**: set `full_refresh=False` via "Launch with config" in Dagit to skip tables already loaded after a crash, instead of starting over.

### 3.2 Postgres — the warehouse

One database (`warehouse`), two schemas:
- `raw` — bronze. Exact copies of source tables, prefixed by source (`shop_*`, `hubspot_*`). Dagster is the only writer.
- `analytics` — silver + gold. Everything dbt builds. dbt is the only writer.

Two more databases exist purely for application state: `dagster` (run history) and `metabase` (dashboards, users, settings) — neither holds business data.

### 3.3 dbt — the transformer

Reads `raw.*`, writes `analytics.*`, in three layers:

| Layer | Materialization | Rule |
|---|---|---|
| `staging/` (silver) | view | 1:1 with a raw source table. Rename columns to snake_case, cast types, decode flags, drop soft-deletes. **No business logic.** |
| `intermediate/` (silver) | view | Reusable joins/aggregations consumed by more than one mart. Not exposed to Metabase. |
| `marts/` (gold) | table | Business-facing, one clear grain per model, all business filters live here. |

Naming convention: `stg_<source>_<entity>`, `int_<purpose>`, `mart_<business_concept>`. A model's name always tells you its layer and, for staging, its source.

After every `dbt build`, a Dagster step pushes every model and column description from `schema.yml` into Metabase's field metadata via `dbt-metabase` — so a business user opens a table in Metabase and sees the same documentation you wrote in dbt, automatically, with no manual step to forget.

### 3.4 Metabase — the BI tool

Connects to `warehouse` / schema `analytics` only — it never touches `raw`. Business users build questions and dashboards against `mart_*` tables. `scripts/add_guardrail_headers.py` demonstrates stamping a "data source & freshness" caveat card onto a dashboard automatically — cheap governance instead of tribal knowledge that a metric has a footnote.

## Part 4 — Extending the stack

**Point at a real source:** change `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` in `.env` to a read-only account, set `MYSQL_SOURCE_PREFIX`, update `dbt/models/sources.yml`. See the `add-source` agent skill.

**Add a new source (database or API):** copy the pattern in `assets_mysql_source.py` (database) or `assets_hubspot.py` (API): one extract-load asset, one schedule, source-specific staging models. Keep failure isolated per source — one source's outage shouldn't block another's schedule.

**Turn an ad-hoc query into a governed model:** don't paste raw SQL into a mart. Decompose it into staging (rename/cast) → intermediate (joins, if reused) → mart (business filters, final grain). See the `adapt-query` agent skill for a guided version of this.
