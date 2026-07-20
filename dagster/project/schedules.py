from dagster import AssetSelection, RunConfig, ScheduleDefinition, define_asset_job

from .assets_mysql_source import MysqlLoadConfig, mysql_raw_load
from .assets_hubspot import HubSpotLoadConfig, hubspot_raw_load

# ── Manual "run everything" job (no schedule — use from Dagit for full reloads) ──
daily_full_pipeline_job = define_asset_job(
    name="daily_full_pipeline_job",
    selection=AssetSelection.all(),
    description="Manual: all EL (MySQL + HubSpot) + dbt in one job.",
)

# ── MySQL source: 03:00 UTC daily ─────────────────────────────────────────────
daily_mysql_ingest_job = define_asset_job(
    name="daily_mysql_ingest_job",
    selection=AssetSelection.assets(mysql_raw_load),
    description="Daily MySQL extract: truncates and reloads all source raw tables.",
)
daily_mysql_3am_schedule = ScheduleDefinition(
    name="daily_mysql_3am",
    job=daily_mysql_ingest_job,
    cron_schedule="0 3 * * *",
    timezone="UTC",
    run_config=RunConfig(ops={"mysql_raw_load": MysqlLoadConfig(full_refresh=True)}),
)

# ── HubSpot: 02:30 UTC daily (optional source — disable if unused) ────────────
daily_hubspot_ingest_job = define_asset_job(
    name="daily_hubspot_ingest_job",
    selection=AssetSelection.assets(hubspot_raw_load),
    description="Daily HubSpot API extract: truncates and reloads companies, deals, owners.",
)
daily_hubspot_230am_schedule = ScheduleDefinition(
    name="daily_hubspot_2_30am",
    job=daily_hubspot_ingest_job,
    cron_schedule="30 2 * * *",
    timezone="UTC",
    run_config=RunConfig(ops={"hubspot_raw_load": HubSpotLoadConfig(full_refresh=True)}),
)

# ── dbt: 04:00 UTC daily (after both extracts) ────────────────────────────────
daily_dbt_job = define_asset_job(
    name="daily_dbt_job",
    selection=AssetSelection.all() - AssetSelection.assets(mysql_raw_load) - AssetSelection.assets(hubspot_raw_load),
    description="Rebuilds all dbt models. Runs after both extract jobs complete (04:00 UTC).",
)
daily_dbt_4am_schedule = ScheduleDefinition(
    name="daily_dbt_4am",
    job=daily_dbt_job,
    cron_schedule="0 4 * * *",
    timezone="UTC",
)
