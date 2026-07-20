---
name: add-source
description: Scaffold a new data source into the stack — Dagster extract-load asset, sources.yml entry, and staging model stubs, following the repo's conventions. Use when the user wants to connect a new database or API to this stack, or point it at their real production source.
---

# add-source

Add a new source to the stack, following the existing database-extract pattern (`assets_mysql_source.py`), or adapting it to an API-extract shape when the new source is API-based rather than a queryable database.

## Stack context

See [AGENTS.md](../../../AGENTS.md) for the full contract. The rule that matters most here: **Dagster owns `raw.*`, dbt only reads it via `source()`.** Never have dbt or the BI tool connect directly to a source system.

## Step 1 — Clarify the shape

Ask (or infer from what the user described):
1. Is this a **database** source (like the bundled MySQL demo — bulk extract all/most tables) or an **API** source (a handful of named objects, paginated, fetched over HTTP)?
2. What should the raw-table prefix be? (`raw.<prefix>_<table>`) — short, lowercase, e.g. `crm`, `billing`, `support`.
3. Is this replacing the bundled demo MySQL source, or adding an additional source alongside it?

## Step 2 — Scaffold the Dagster asset

**Database source** — copy `dagster/project/assets_mysql_source.py` as a template:
- New file `dagster/project/assets_<prefix>.py` (or edit `assets_mysql_source.py` in place if replacing the demo source)
- Change the connection env vars to source-specific names (e.g. `CRM_MYSQL_HOST` instead of reusing `MYSQL_HOST`, once there's more than one database source)
- Set `SOURCE_PREFIX` to the chosen prefix
- Review `SKIP_TABLES` — start empty and add entries as you find tables that are too large, irrelevant, or pure application noise

**API source** — there's no bundled example in this template, but the shape to follow is the same as the database asset:
- New file `dagster/project/assets_<prefix>.py`, one `@asset` function per source (or one for the whole source if it's a handful of objects)
- Guard the top of the asset function on the credential env var being set, and `return` early with a log warning if it isn't — every optional source should self-skip cleanly, not fail the run
- Paginate according to the API's actual mechanism (cursor, offset, page token) and write each page to Postgres incrementally, mirroring the chunked-write pattern in `assets_mysql_source.py`, so memory stays flat regardless of record count

Register the new asset in `dagster/project/definitions.py` (add to `assets=[...]`) and add a job + schedule in `dagster/project/schedules.py`, following the existing per-source job pattern — do not fold it into `daily_full_pipeline_job`'s selection logic in a way that breaks source-level failure isolation.

## Step 3 — Register the source in dbt

Add an entry to `dbt/models/sources.yml` under a new `- name: <prefix>` block, listing every raw table you expect Dagster to produce. Include `freshness` if the source has a schedule, and `data_tests: [unique, not_null]` on primary keys.

## Step 4 — Scaffold staging models

For each raw table the user actually needs (don't build staging models for tables nobody queries yet):

`dbt/models/staging/stg_<prefix>_<table>.sql`
- One `source` CTE, one `cleaned` CTE (or a plain `select` for very simple tables), `select * from cleaned`
- Rename every column to human-readable snake_case
- Cast types explicitly (`::timestamp`, `::numeric`, boolean coercions)
- Drop soft-deleted rows if the source has that concept
- **No business filters here** — those belong in the mart

If this is an optional source (one that can be unconfigured), gate its model folder in `dbt_project.yml` with an `+enabled: "{{ (env_var('<SOURCE>_TOKEN', '') != '') | as_bool }}"` config keyed off the same credential env var the Dagster asset checks — so `dbt build` doesn't fail when the source isn't configured.

## Step 5 — Tell the user what's next

State clearly:
- Files created/modified
- What env vars need to be set in `.env` before this source will extract successfully
- That marts still need to be built by hand (or via `adapt-query` if working from a specific business question) — this skill only gets data to the staging layer
- Suggest running `refresh-stack` once credentials are in place to verify the extract and build actually work
