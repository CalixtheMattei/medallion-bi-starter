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

Trigger the `mysql_raw_load` asset. Prefer the CLI so this skill doesn't depend on clicking through Dagit:

```bash
docker compose exec -T dagster_user_code dagster asset materialize \
  --select mysql_raw_load -m project -w /var/lib/dagster/workspace.yaml
```

If that command isn't available in the image, tell the user to open Dagit → http://localhost:3001 → Assets → select `mysql_raw_load` → Materialize.

Verify raw tables landed:
```bash
docker compose exec -T postgres psql -U postgres -d warehouse -c "\dt raw.*"
```
Expect `shop_customers`, `shop_products`, `shop_orders`, `shop_order_items`.

### 5 — Build the dbt models

```bash
docker compose run --rm --no-deps --entrypoint dbt dagster_user_code build \
  --project-dir /dbt --profiles-dir /dbt
```

Expect `CREATE VIEW` for staging/intermediate models and `SELECT N` for marts.

### 6 — Verify a mart has rows

```bash
docker compose exec -T postgres psql -U postgres -d warehouse \
  -c "SELECT activity_status, count(*) FROM analytics.mart_customer_activity GROUP BY 1;"
```

You should see a handful of customers across `active` / `slowing` / `dormant` / `never_ordered`. If the table doesn't exist or is empty, stop and debug — don't proceed to Metabase with an empty pipeline.

### 7 — Metabase setup

Open http://localhost:3000. On first load Metabase runs its setup wizard:
- Use the `METABASE_USER` / `METABASE_PASSWORD` from `.env` as the admin account
- Add a database: Postgres, host `postgres`, port `5432`, database `warehouse`, schema filter `analytics`, using `POSTGRES_USER` / `POSTGRES_PASSWORD` from `.env`

After the dbt build in step 5, model and column descriptions are already synced into Metabase automatically (via `dbt-metabase`, triggered by the `dbt_project_assets` Dagster asset) — the user should see them as table/field descriptions once the database is added.

## Report to the user

- Which services are healthy
- Raw tables confirmed present
- dbt build result (models built, any errors)
- Mart row counts by activity_status
- Next step: open Metabase and finish the setup wizard, or hand off to the `create-dashboard` skill to build the first dashboard
