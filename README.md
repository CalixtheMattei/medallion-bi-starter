# Medallion BI Starter

A Docker Compose starter for an **open-source BI stack**: Dagster for orchestration, Postgres as the warehouse, dbt for transformation and governance, Metabase for self-serve analytics — wired together with a medallion (bronze/silver/gold) architecture.

It ships with a synthetic e-commerce demo dataset so the whole pipeline runs end-to-end with `docker compose up` and **zero external credentials**. Swap in your own source database when you're ready — the pattern doesn't change, only the connection details do.

```
[Source: MySQL]
  (bundled demo: synthetic e-commerce data — swap for your own database)
            │
            ▼
        [Dagster]
   source-specific extract/load
            │
            ▼
    raw.<source>_<entity>        (Bronze)
            │
            ▼
   analytics.stg_<source>_*      (Silver)
   analytics.int_*               (Intermediate)
   analytics.mart_*              (Gold)
            │
            ▼
        [Metabase]
```

**UIs available after startup:**
| UI       | URL                   | What you do there                              |
|----------|-----------------------|-------------------------------------------------|
| Dagit    | http://localhost:3001 | Materialize assets, browse lineage, view logs   |
| Metabase | http://localhost:3000 | Query and visualize analytics models            |

---

## Why this exists

Most BI starter templates show you a dbt project against a static CSV. This one shows the full loop a real analytics team lives in: an operational source database gets extracted on a schedule, lands as raw bronze tables, gets cleaned into silver staging views, gets aggregated into gold marts with explicit governance rules, and surfaces in a BI tool with descriptions and freshness guardrails attached automatically.

If you're evaluating whether Dagster + dbt + Postgres + Metabase can work as your team's internal analytics stack, this repo is meant to be a working reference you can run, poke at, and adapt — not just read.

## What's demonstrated

- **A database source pattern**: chunked extraction with resume-on-crash, ready to point at a real MySQL instance (see the `add-source` skill for adapting the pattern to an API source too).
- **Medallion layering with enforced rules**: staging views never contain business logic; marts never query raw tables directly; naming conventions make the layer of any model obvious at a glance.
- **Semantic layer sync**: dbt column descriptions push automatically into Metabase field metadata after every build, so a business user sees documentation in the BI tool without anyone maintaining it twice.
- **Governance-as-code**: a small script (`scripts/add_guardrail_headers.py`) that stamps a "data source & freshness" caveat card onto dashboards — cheap, repeatable governance instead of tribal knowledge.
- **AI-agent-operable**: ships with Claude/Codex-compatible agent skills (see below) to launch the stack, add a new source, and turn an ad-hoc SQL query into a proper governed model.

## Quick start

```bash
git clone <this-repo>
cd medallion-bi-starter
cp .env.example .env
docker compose up -d --build
```

Then:
1. Open Dagit → http://localhost:3001
2. Materialize `mysql_raw_load` (loads the demo e-commerce data into `raw.*`)
3. Materialize all dbt assets (builds `analytics.stg_*` → `analytics.mart_*`)
4. Open Metabase → http://localhost:3000, finish the setup wizard using the credentials from `.env`, connect it to the `warehouse` Postgres database (schema `analytics`)

If you have an AI coding agent (Claude Code, Codex) available, the `setup` skill in [.claude/skills/](.claude/skills/) walks through all of this for you — see [Agent skills](#agent-skills) below.

## Pointing at a real source

Everything above runs against the bundled `mysql-demo` container. To extract from your own MySQL database instead:

1. Edit `.env`: set `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` to a **read-only** account on your database
2. Set `MYSQL_SOURCE_PREFIX` to a short name for the source (e.g. `crm`, `billing`) — raw tables land as `raw.<prefix>_<table>`
3. Update `dbt/models/sources.yml` to match your table names
4. Review `SKIP_TABLES` in `dagster/project/assets_mysql_source.py` — exclude tables that are too large, irrelevant, or pure application noise

Nothing else in the stack needs to change. See the `add-source` agent skill for a guided version of this.

## Repository layout

```
dagster/           Dagster user code: extract/load assets, schedules, Dockerfile
dbt/                dbt project: staging → intermediate → marts, sources.yml, seeds
demo-source/        Synthetic e-commerce seed data (deterministic, safe to commit)
docs/               Architecture guide and mart reference
scripts/            One-off Metabase automation (guardrail headers, etc.)
.claude/skills/      Agent skills for Claude Code / Codex — see below
```

## Agent skills

This repo ships a set of skills for AI coding agents (compatible with Claude Code and Codex via `AGENTS.md`) that encode how to operate the stack:

| Skill | What it does |
|---|---|
| `setup` | Guided first launch: build, materialize demo assets, verify a mart has rows |
| `add-source` | Scaffold a new source: Dagster asset + `sources.yml` entry + staging model stubs |
| `adapt-query` | Take a raw, ad-hoc SQL query and turn it into a proper staging model + mart, following the layer rules |
| `refresh-stack` | Run dbt for new/changed models, validate types, sync Metabase |
| `create-dashboard` | Build a Metabase dashboard from a mart via the REST API |

See `AGENTS.md` for the conventions these skills rely on.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — full architecture walkthrough, service-by-service
- [docs/MART_REFERENCE.md](docs/MART_REFERENCE.md) — plain-English reference for each mart, written for a business/analytics reader

## Roadmap ideas

- [ ] Move secrets from `.env` to a proper secrets manager for any non-local deployment
- [ ] Add a `dbt test` CI job (GitHub Actions) that runs against a throwaway Postgres
- [ ] Add a third source demonstrating a file/CSV-drop pattern (S3, SFTP)
- [ ] Add row-level dbt tests beyond `unique`/`not_null`

## License

MIT — see [LICENSE](LICENSE). Use this as a starting point for your own stack.
