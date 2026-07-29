"""
MySQL Extract-Load asset — the "database source" pattern.

Streams every table from a source MySQL database into the warehouse raw
schema as `<prefix>_<table_name>`, using chunked reads to keep memory flat
regardless of table size.

Out of the box this points at the bundled `mysql-demo` container (a synthetic
e-commerce database). To extract from a real production MySQL instead, change
the MYSQL_* variables in `.env` — nothing in this file needs to change.

RESUMABLE: tables already present in the raw schema are skipped when
full_refresh=False. Re-run after a crash to continue from where it stopped.
To force a full reload of everything:
  docker compose exec postgres psql -U postgres -d warehouse -c \
    "DROP SCHEMA raw CASCADE; CREATE SCHEMA raw;"
Then re-materialize.
"""

import json
import os

import pandas as pd
import sqlalchemy.exc
from sqlalchemy import create_engine, inspect, text

from dagster import AssetExecutionContext, Config, RetryPolicy, asset

from .utils import pg_engine as _pg_engine

CHUNK_SIZE = 5_000  # rows per batch — keeps memory flat regardless of table size

# Prefix for landed tables: raw.<prefix>_<table>. Also referenced in
# dbt/models/sources.yml — keep the two in sync if you change it.
SOURCE_PREFIX = os.environ.get("MYSQL_SOURCE_PREFIX", "shop")

# Tables to skip — add source tables here that are irrelevant for analytics,
# too large to copy, or pure application noise (UI config, media blobs,
# framework bookkeeping…). On a real production source this list grows fast;
# reviewing it regularly is part of pipeline hygiene.
SKIP_TABLES: set[str] = {
    # "some_huge_event_log",      # example: unbounded event table, no analytics value
    # "framework_migrations",     # example: ORM/migration bookkeeping
}


def _mysql_engine():
    return create_engine(
        f"mysql+pymysql://{os.environ['MYSQL_USER']}:{os.environ['MYSQL_PASSWORD']}"
        f"@{os.environ['MYSQL_HOST']}:{os.environ.get('MYSQL_PORT', '3306')}"
        f"/{os.environ['MYSQL_DATABASE']}",
        connect_args={"connect_timeout": 15, "read_timeout": 600},
    )


def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """Fix MySQL→Postgres incompatibilities per chunk:
    1. NUL bytes (\\x00) in strings — Postgres TEXT rejects them.
    2. Python dicts/lists (JSON columns) — serialize to JSON strings.
    3. Python bytes (MySQL tinyint(1) via pymysql) — convert to int so
       TRUNCATE+append into existing bigint columns doesn't type-mismatch.
    """
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].apply(
            lambda v: int.from_bytes(v, "big") if isinstance(v, bytes)
            else json.dumps(v, default=str) if isinstance(v, (dict, list))
            else v
        )
        df[col] = df[col].apply(
            lambda v: v.replace("\x00", "") if isinstance(v, str) else v
        )
    return df


class MysqlLoadConfig(Config):
    full_refresh: bool = True
    """
    True  (default): truncate each raw table before reloading — always fresh data.
                     Used by the daily schedule.
    False           : skip tables already present — use this to resume after a crash.
                     Set via Dagit "Launch with config" when re-running manually.
    """


@asset(
    group_name="extract_load",
    compute_kind="mysql",
    retry_policy=RetryPolicy(max_retries=2, delay=30),
)
def mysql_raw_load(context: AssetExecutionContext, config: MysqlLoadConfig):
    """
    Streams all source MySQL tables → warehouse raw schema as `<prefix>_<table>`.

    full_refresh=True  (daily schedule): truncates each table before reloading so
                       data is always current.
    full_refresh=False (crash recovery): skips tables already present so the run
                       continues from where it stopped. Set manually in Dagit.
    """
    mysql = _mysql_engine()
    pg = _pg_engine()

    mysql_inspector = inspect(mysql)
    pg_inspector = inspect(pg)

    all_tables = mysql_inspector.get_table_names()

    # Snapshot of tables already in raw schema before this run
    already_loaded = {
        t for t in pg_inspector.get_table_names(schema="raw")
        if t.startswith(f"{SOURCE_PREFIX}_")
    }
    mode = "full_refresh (truncate + reload)" if config.full_refresh else "resume (skip existing)"
    context.log.info(
        f"Mode: {mode}. "
        f"Found {len(all_tables)} MySQL tables. "
        f"{len(already_loaded)} already in raw schema. "
        f"{len(SKIP_TABLES)} in blocklist (will skip)."
    )

    loaded, resumed, errored, ignored = [], [], [], []

    for table in all_tables:
        target = f"{SOURCE_PREFIX}_{table}"

        if table in SKIP_TABLES:
            ignored.append(table)
            continue

        if target in already_loaded:
            if not config.full_refresh:
                resumed.append(table)
                context.log.info(f"  SKIP {table} -> already in raw.{target} (resume mode)")
                continue
            # full_refresh: the chunk loop below handles the initial TRUNCATE

        try:
            total_rows = 0
            offset = 0
            # No explicit TRUNCATE needed: the first chunk below uses
            # if_exists="replace", which drops and recreates the table — so a
            # retry (which always restarts at offset 0) starts from a clean slate.
            first_chunk = True
            while True:
                chunk = pd.read_sql(
                    f"SELECT * FROM `{table}` LIMIT {CHUNK_SIZE} OFFSET {offset}",
                    mysql,
                )
                if chunk.empty:
                    break
                chunk = _sanitize(chunk)
                chunk.to_sql(
                    target, pg, schema="raw",
                    if_exists="replace" if first_chunk else "append",
                    index=False,
                )
                first_chunk = False
                total_rows += len(chunk)
                offset += CHUNK_SIZE
                context.log.info(f"  {table}: {total_rows:,} rows so far")
                if len(chunk) < CHUNK_SIZE:
                    break

            cols = [c["name"] for c in mysql_inspector.get_columns(table)]
            context.log.info(
                f"  OK {table} -> raw.{target}  ({total_rows:,} rows)  columns: {cols}"
            )
            loaded.append(table)

        except sqlalchemy.exc.OperationalError as exc:
            context.log.error(f"  DB connection error on {table}: {exc}", exc_info=True)
            errored.append(table)
            raise  # surface to Dagster so the retry policy can fire
        except sqlalchemy.exc.SQLAlchemyError as exc:
            context.log.error(f"  DB error on {table}: {exc}", exc_info=True)
            errored.append(table)
            raise
        except Exception as exc:
            context.log.error(f"  Unexpected error on {table}: {exc}", exc_info=True)
            errored.append(table)
            raise

    context.log.info(
        f"\nDone: {len(loaded)} newly loaded, {len(resumed)} already present, "
        f"{len(errored)} errors, {len(ignored)} blocklisted."
        f"\nErrors: {errored}"
    )

    with pg.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name, pg_size_pretty(pg_total_relation_size("
            "('raw.' || quote_ident(table_name))::regclass)) AS size "
            "FROM information_schema.tables "
            "WHERE table_schema = 'raw' AND table_name LIKE :pattern "
            "ORDER BY table_name"
        ), {"pattern": f"{SOURCE_PREFIX}_%"}).fetchall()
    context.log.info(f"\nAll {len(rows)} source tables now in raw schema:")
    for r in rows:
        context.log.info(f"  raw.{r[0]}  {r[1]}")
