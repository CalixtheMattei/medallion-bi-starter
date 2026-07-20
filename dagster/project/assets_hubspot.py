"""
HubSpot Extract-Load asset — the "API source" pattern (optional second source).

Fetches Companies, Deals, and Owners from the HubSpot CRM API and writes them
to the warehouse raw schema as `hubspot_company`, `hubspot_deal`, `hubspot_owner`.

OPTIONAL: if HUBSPOT_ACCESS_TOKEN is not set in .env, the asset skips itself —
the demo stack works fully without it. The matching dbt models are also
disabled automatically (see models/staging/hubspot/ config in dbt_project.yml).

All property values arrive as strings from the API — the staging layer handles casting.
RESUMABLE: set full_refresh=False in Dagit to skip already-loaded tables after a crash.
"""

import os

import pandas as pd
import requests as http
from sqlalchemy import text

import hubspot

from dagster import AssetExecutionContext, Config, RetryPolicy, asset

from .utils import pg_engine as _pg_engine

HS_API_BASE = "https://api.hubapi.com"
HS_CRM_BATCH_SIZE = 100   # HubSpot batch/read endpoint limit per request
HS_OWNERS_PAGE_SIZE = 500  # Owners API supports larger pages than CRM objects


def _hs_client() -> hubspot.Client:
    return hubspot.Client.create(access_token=os.environ["HUBSPOT_ACCESS_TOKEN"])


def _hs_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


def _stream_crm_object(
    client: hubspot.Client,
    object_type: str,
    table_name: str,
    pg,
    full_refresh: bool,
    context: AssetExecutionContext,
) -> int:
    """Fetch and write a CRM object type to Postgres in a streaming fashion.

    Collects all IDs first (list GET with single property — no 414, no 10K cap),
    then batch-reads properties in chunks of 100 and writes each chunk immediately
    to Postgres — keeping memory flat regardless of record count.

    Returns the number of rows written.
    """
    props_response = client.crm.properties.core_api.get_all(object_type)
    prop_names = [p.name for p in props_response.results]
    context.log.info(f"  {object_type}: {len(prop_names)} properties available")

    # Step 1: collect all IDs (GET with single property = no 414, cursor has no cap)
    all_ids = []
    after = None
    while True:
        result = getattr(client.crm, object_type).basic_api.get_page(
            limit=100, properties=["hs_object_id"], after=after,
        )
        all_ids.extend(o.id for o in result.results)
        if result.paging and result.paging.next:
            after = result.paging.next.after
        else:
            break
    context.log.info(f"  {object_type}: {len(all_ids):,} IDs collected")

    # Step 2: batch read properties + stream write to Postgres (100 rows at a time)
    total_written = 0
    first_chunk = True
    for i in range(0, len(all_ids), HS_CRM_BATCH_SIZE):
        chunk = all_ids[i:i + HS_CRM_BATCH_SIZE]
        resp = http.post(
            f"{HS_API_BASE}/crm/v3/objects/{object_type}/batch/read",
            headers=_hs_headers(),
            json={"properties": prop_names, "inputs": [{"id": id_} for id_ in chunk]},
            timeout=60,
        )
        resp.raise_for_status()
        rows = [
            {"hs_object_id": o.get("id"), **o.get("properties", {})}
            for o in resp.json().get("results", [])
            if o.get("id") is not None
        ]
        if not rows:
            continue

        chunk_df = pd.DataFrame(rows)
        # First chunk: replace (creates/resets the table). Subsequent: append.
        chunk_df.to_sql(
            table_name, pg, schema="raw",
            if_exists="replace" if (first_chunk and full_refresh) else "append",
            index=False,
        )
        first_chunk = False
        total_written += len(rows)
        context.log.info(f"  {object_type}: {total_written:,}/{len(all_ids):,} written to DB…")

    return total_written


def _fetch_owners(client: hubspot.Client, context: AssetExecutionContext) -> pd.DataFrame:
    """Fetch all HubSpot owners (AEs, CSMs). Different API — not cursor-paginated for typical sizes."""
    all_rows = []
    after = None
    while True:
        result = client.crm.owners.owners_api.get_page(limit=HS_OWNERS_PAGE_SIZE, after=after)
        all_rows.extend({
            "id": str(o.id),
            "email": o.email,
            "first_name": o.first_name,
            "last_name": o.last_name,
            "user_id": str(o.user_id) if o.user_id else None,
            "created_at": str(o.created_at) if o.created_at else None,
            "updated_at": str(o.updated_at) if o.updated_at else None,
        } for o in result.results)
        if result.paging and result.paging.next:
            after = result.paging.next.after
        else:
            break

    context.log.info(f"  owners: {len(all_rows):,} records fetched")
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


class HubSpotLoadConfig(Config):
    full_refresh: bool = True
    """
    True  (default): truncate each raw table before reloading — always fresh data.
                     Used by the daily schedule.
    False           : skip tables already present — use this to resume after a crash.
                     Set via Dagit "Launch with config" when re-running manually.
    """


@asset(
    group_name="extract_load",
    compute_kind="hubspot_api",
    retry_policy=RetryPolicy(max_retries=2, delay=30),
)
def hubspot_raw_load(context: AssetExecutionContext, config: HubSpotLoadConfig):
    """
    Fetches HubSpot Companies, Deals, and Owners → warehouse raw schema.

    full_refresh=True  (daily schedule): truncates before reloading — always current.
    full_refresh=False (crash recovery): skips tables already present.
    """
    if not os.environ.get("HUBSPOT_ACCESS_TOKEN"):
        context.log.warning(
            "HUBSPOT_ACCESS_TOKEN not set — skipping HubSpot extract. "
            "Set it in .env to enable this optional source."
        )
        return

    client = _hs_client()
    pg = _pg_engine()

    # (object_type for API, raw table name)
    CRM_OBJECTS = [
        ("companies", "hubspot_company"),
        ("deals",     "hubspot_deal"),
    ]

    loaded = []
    errored = []

    for object_type, table_name in CRM_OBJECTS:
        context.log.info(f"Fetching {object_type} → raw.{table_name} …")
        try:
            if not config.full_refresh and _table_exists(pg, table_name):
                context.log.info(f"  raw.{table_name} already exists — skipping (resume mode)")
                continue

            n = _stream_crm_object(client, object_type, table_name, pg, config.full_refresh, context)
            context.log.info(f"  OK raw.{table_name}  ({n:,} rows)")
            loaded.append(table_name)

        except http.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (429, 503):
                context.log.error(
                    f"  HubSpot rate-limit/unavailable (HTTP {status}) on {object_type} — "
                    "will retry via Dagster retry policy",
                    exc_info=True,
                )
            elif status in (401, 403):
                context.log.error(
                    f"  HubSpot auth error (HTTP {status}) on {object_type} — check HUBSPOT_ACCESS_TOKEN",
                    exc_info=True,
                )
            else:
                context.log.error(f"  HubSpot HTTP error on {object_type}: {exc}", exc_info=True)
            errored.append(table_name)
            raise  # surface to Dagster so the retry policy can fire
        except Exception as exc:
            context.log.error(f"  Unexpected error on {object_type}: {exc}", exc_info=True)
            errored.append(table_name)
            raise

    # Owners
    context.log.info("Fetching owners -> raw.hubspot_owner …")
    try:
        df_owners = _fetch_owners(client, context)
        if not df_owners.empty:
            if config.full_refresh or not _table_exists(pg, "hubspot_owner"):
                df_owners.to_sql("hubspot_owner", pg, schema="raw", if_exists="replace", index=False)
                context.log.info(
                    f"  OK raw.hubspot_owner  ({len(df_owners):,} rows, {len(df_owners.columns)} columns)"
                )
                loaded.append("hubspot_owner")
            else:
                context.log.info("  SKIP raw.hubspot_owner already exists (resume mode)")
    except http.exceptions.HTTPError as exc:
        context.log.error(f"  HubSpot HTTP error fetching owners: {exc}", exc_info=True)
        errored.append("hubspot_owner")
        raise
    except Exception as exc:
        context.log.error(f"  Unexpected error fetching owners: {exc}", exc_info=True)
        errored.append("hubspot_owner")
        raise

    context.log.info(
        f"\nDone: {len(loaded)} loaded, {len(errored)} errors."
        f"\nErrors: {errored}"
    )

    # Summary of what's now in raw
    with pg.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name, pg_size_pretty(pg_total_relation_size("
            "('raw.' || quote_ident(table_name))::regclass)) AS size "
            "FROM information_schema.tables "
            "WHERE table_schema = 'raw' AND table_name LIKE 'hubspot_%' "
            "ORDER BY table_name"
        )).fetchall()
    context.log.info(f"\nAll {len(rows)} HubSpot tables now in raw schema:")
    for r in rows:
        context.log.info(f"  raw.{r[0]}  {r[1]}")


def _table_exists(pg_engine, table_name: str) -> bool:
    with pg_engine.connect() as conn:
        result = conn.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='raw' AND table_name=:t"
        ), {"t": table_name}).fetchone()
    return result is not None
