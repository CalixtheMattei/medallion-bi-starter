# AGENTS.md

This repository-level guidance applies to Codex, Claude, and other coding agents working in this repo. It's the single source of truth for conventions — the `.claude/skills/` skills reference it rather than duplicating it.

## Purpose

This repository is an open-source BI starter: a medallion-architecture data platform built on Dagster, dbt, Postgres, and Metabase, meant to be forked and adapted to a real source.

Out of the box it ingests one bundled demo source: a synthetic e-commerce MySQL database. The intent is for a user to swap it for their own database with minimal changes, then add further sources (database or API) following the same pattern — see the `add-source` skill.

High-level flow:

1. Dagster extracts source data into Postgres `raw.*`
2. dbt builds cleaned `stg_*` views, reusable `int_*` views, and business-facing `mart_*` tables in Postgres `analytics.*`
3. Metabase reads `analytics.*` for dashboards and self-serve analysis

This is not a product app. Treat it as a local-first warehouse and BI repo designed to be extended source by source.

## Key Directories

- `dagster/`: Dagster code, asset definitions, schedule definitions, Docker image for the code server.
- `dbt/`: dbt project, models, macros, profiles, seeds, compiled artifacts.
- `demo-source/`: synthetic seed data for the bundled MySQL demo source (deterministic, safe to regenerate/edit).
- `docs/`: architecture and mart documentation.
- `docker-compose.yml`: local stack entrypoint.
- `init-db.sh`: Postgres bootstrap for `warehouse`, `dagster`, and `metabase` databases.
- `.claude/skills/`: agent skills for operating and extending this stack.

## Working Rules

### Respect the warehouse contract

- Dagster owns writes to `raw.*`.
- dbt reads from `raw.*` via `source()`.
- dbt writes to `analytics.*`.
- Marts should read from `ref('stg_*')` and `ref('int_*')`, not directly from `source()`, unless there is a deliberate exception and it is documented.
- Keep ingestion and staging source-specific; keep marts business-first.

### Preserve the model layering

- `staging/`: source-faithful cleanup only. Rename columns, cast types, normalize booleans, filter soft deletes. No business logic.
- `intermediate/`: reusable joins or heavier reshaping used by more than one downstream consumer.
- `marts/`: business-facing tables at a clear grain, optimized for Metabase and stakeholder questions.

As new sources are added:

- prefer `raw.<source>_<entity>`
- prefer `stg_<source>_<entity>`
- use `int_<source>_<purpose>` for source-specific intermediate logic
- use shared `int_<business_concept>` models only when more than one source contributes to that concept

### Keep docs aligned with behavior

If you change runtime behavior, also update the relevant docs:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/MART_REFERENCE.md` when model semantics or business meaning change

Do not leave docs describing a manual process if the code is automated, or vice versa.

### Treat generated files as generated

Avoid editing generated artifacts by hand unless the user explicitly asks:

- `dbt/target/**`
- `dbt/logs/**`

Do not commit or rely on generated output as the source of truth for behavior.

### Be careful with existing workspace changes

The working tree may already contain user changes. Do not revert or overwrite unrelated modifications unless the user explicitly asks.

## Repo-Specific Expectations

### dbt

- Prefer adding or updating `schema.yml` docs/tests alongside new models.
- Source-level tests exist (`unique`, `not_null` on primary keys); model-level tests are still sparse. If you add important business logic, add the most relevant tests you can.
- Business thresholds (activity windows, lookback periods) belong in `dbt_project.yml` vars, not hardcoded in SQL — see `activity_active_days` / `activity_slowing_days` for the existing pattern.

### Dagster

- `mysql_raw_load` is the core extract-load asset. It's a full truncate-and-reload copy, not incremental replication — see "What 'extract' means here" in `docs/ARCHITECTURE.md` before assuming otherwise.
- Scheduling behavior lives in `dagster/project/schedules.py`. The dbt build schedule runs a fixed offset after the extract schedule, not back-to-back — see "Scheduling" in `docs/ARCHITECTURE.md` for why, and reconsider that offset (or move to an event-driven trigger) if extract runtime grows.
- If you change refresh cadence or timezone semantics, update both code and docs explicitly.
- When adding a second source, prefer one extract/load asset (or asset group) per source, with source-specific jobs and schedules, so one source's failure doesn't block another's.

### SQL and analytics semantics

- Favor explicit grains in marts, and state them in comments.
- Keep business-readable names in staging so downstream SQL stays readable.
- When adapting an ad-hoc SQL query into the stack, convert it into layered dbt models (staging → intermediate → mart) rather than copying raw SQL into a mart unchanged — see the `adapt-query` skill.
- If a model is source-specific, keep that visible in the name.
- If a model is cross-source, keep it business-named and document which sources feed it.

## Verification

When you make relevant changes, prefer the smallest useful validation:

- `dbt parse` for project integrity
- targeted `dbt run --select ...` for changed models
- targeted `dbt test --select ...` when tests exist

If you cannot run validation, say so clearly.

## Security and data handling

- Do not expose secrets from `.env`.
- Treat `.env` and local credentials as operator-managed files; do not rewrite them unless explicitly asked.
- As more sources are added, prefer namespaced env vars (e.g. `<SOURCE>_*`) instead of generic shared names.
- If you point this stack at a real production source, only ever use a read-only account, and never add code that writes back to a source system.
