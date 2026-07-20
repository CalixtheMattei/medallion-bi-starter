---
name: adapt-query
description: Audit a raw, ad-hoc SQL query against a source database, check the existing dbt models and Metabase dashboards, then integrate it into the stack as proper layered dbt models (staging + mart). Use when a user has a one-off SQL query they want turned into a governed, repeatable model.
---

# adapt-query

Given a raw SQL query written against a source database (or a description of "the query I keep running by hand"), audit it, cross-check the current dbt stack and Metabase dashboards, and produce the dbt models needed to replace it properly.

## Stack context

- **Raw layer**: Dagster copies source tables to `raw.*` automatically — no action needed unless a table is in that source's `SKIP_TABLES` (check the relevant `dagster/project/assets_*.py`)
- **dbt layers**: `staging/` (views, 1:1 with source) → `intermediate/` (complex joins, reused by multiple marts) → `marts/` (tables, queried by Metabase)
- **Metabase**: connects to `analytics.mart_*` only — never to `raw.*`
- **Governance rules** (see [AGENTS.md](../../../AGENTS.md) for the full list):
  - Marts never query `raw.*` directly — always via `{{ ref('stg_...') }}`
  - Staging models rename columns; marts never touch raw column names
  - Staging = VIEW, marts = TABLE
  - Business thresholds (activity windows, lookback periods) live in `dbt_project.yml` vars, not hardcoded in SQL

## Instructions

### Step 1 — Audit the query

Read and understand the query provided. Identify:
- Which source tables it touches
- What filters it applies (status codes, deleted flags, date ranges, etc.)
- What aggregation or shape it produces
- Any code smells: repeated `UNION ALL` blocks, raw column names bleeding into the final output, correlated subqueries, missing indexes

### Step 2 — Check the dbt stack

Run these in parallel:
1. Read `dbt/models/sources.yml` — are the source tables already registered?
2. Glob `dbt/models/**/*.sql` — do staging and/or mart models already exist for these tables?
3. If a mart already exists answering the same or a similar business question, read it and compare before building a duplicate.

For each source table the query touches:
- Is it in `sources.yml`? If not, add it.
- Is it in that source's `SKIP_TABLES`? If so, flag it — Dagster won't have copied it, and this needs to be resolved before the model can build.
- Is there already a staging model? Does it expose the columns this query needs?

### Step 3 — Assess Metabase coverage

Read `docs/ARCHITECTURE.md` and `docs/MART_REFERENCE.md` to see what marts and dashboards already exist. Ask: is there already a mart/dashboard answering the same business question? If yes, flag it to the user before building anything new — extending an existing mart is usually better than a near-duplicate.

### Step 4 — Plan the dbt changes

Decide what to build:
- **New source registration only** — the table is missing from `sources.yml` but a staging model already covers the shape
- **Staging + mart** — a new source table needs both layers
- **Mart only** — source + staging already exist, only the aggregation is missing
- **Refactor an existing mart** — it exists but doesn't cover this use case; extend it rather than forking it

State the plan explicitly to the user before writing any files.

### Step 5 — Build the staging model (if needed)

File: `dbt/models/staging/stg_<source>_<table>.sql`

- One CTE named `source`, one named `cleaned`, `select * from cleaned`
- Rename every column to human-readable snake_case
- Cast types: `::timestamp`, `::numeric`, boolean coercions (`(col = 1) as is_flag`)
- Fix known source-system quirks in column naming (document the fix in a comment)
- Do NOT filter by business logic (status, region, tier) — that belongs in the mart
- Header comment: what the raw table is, what this model exposes
- Materialize as VIEW (default in `dbt_project.yml` — no `{{ config() }}` needed)

### Step 6 — Build the mart

File: `dbt/models/marts/mart_<descriptive_name>.sql`

- `{{ config(materialized='table') }}`
- Reference `{{ ref('stg_...') }}` for all inputs — never `{{ source(...) }}`
- Apply business filters here (status, region, tier, soft-delete already handled upstream)
- Replace repetitive `UNION ALL` patterns with a `LATERAL VALUES` unpivot where it simplifies the SQL
- One row per meaningful business entity (customer, customer × category, deal, etc.)
- Include enough dimensions for Metabase to slice by
- Header comment: what business questions this mart answers and what ad-hoc query it replaces

### Step 7 — Register the source (if new)

In `dbt/models/sources.yml`, add under the relevant source:

```yaml
- name: <source>_<table_name>
  description: >
    <one paragraph: what this table is, what mart it powers>
  columns:
    - name: id
      description: "Primary key."
      data_tests: [unique, not_null]
```

### Step 8 — Document the mart

Add the mart's description and column docs to the matching `schema.yml` (this is what syncs into Metabase), and add an entry to `docs/MART_REFERENCE.md` following the existing three-part shape: what question it answers, what each non-obvious column means, one caveat.

### Step 9 — Report to the user

Summarize:
- What the original query was doing (plain English)
- What was missing from the stack (source registration, staging, mart)
- What was built (files created/modified)
- Metabase next step: suggest running `create-dashboard` against the new mart, with the columns to use
- Any caveats (typos fixed, columns added to existing staging models, etc.)
