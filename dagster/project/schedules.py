from dagster import AssetSelection, RunConfig, ScheduleDefinition, define_asset_job

from .assets_mysql_source import MysqlLoadConfig, mysql_raw_load

# ── Manual "run everything" job (no schedule — use from Dagit for full reloads) ──
daily_full_pipeline_job = define_asset_job(
    name="daily_full_pipeline_job",
    selection=AssetSelection.all(),
    description="Manual: EL extract + dbt build in one job.",
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
    execution_timezone="UTC",
    run_config=RunConfig(ops={"mysql_raw_load": MysqlLoadConfig(full_refresh=True)}),
)

# ── dbt: 04:00 UTC daily ───────────────────────────────────────────────────────
# The one-hour gap after the 03:00 extract is deliberate, not arbitrary — see
# "Scheduling: why the extract and the build don't run back-to-back" in
# docs/ARCHITECTURE.md. As the source grows, revisit whether one hour is still
# enough headroom, or move to an event-driven trigger instead of a fixed offset.
daily_dbt_job = define_asset_job(
    name="daily_dbt_job",
    selection=AssetSelection.all() - AssetSelection.assets(mysql_raw_load),
    description="Rebuilds all dbt models. Runs after the extract job completes (04:00 UTC).",
)
daily_dbt_4am_schedule = ScheduleDefinition(
    name="daily_dbt_4am",
    job=daily_dbt_job,
    cron_schedule="0 4 * * *",
    execution_timezone="UTC",
)
