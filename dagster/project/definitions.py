from dagster import Definitions
from dagster_dbt import DbtCliResource

from .assets import dbt_project_assets
from .assets_mysql_source import mysql_raw_load
from .assets_hubspot import hubspot_raw_load
from .schedules import (
    daily_full_pipeline_job,
    daily_mysql_ingest_job,
    daily_hubspot_ingest_job,
    daily_dbt_job,
    daily_mysql_3am_schedule,
    daily_hubspot_230am_schedule,
    daily_dbt_4am_schedule,
)

defs = Definitions(
    assets=[dbt_project_assets, mysql_raw_load, hubspot_raw_load],
    jobs=[daily_full_pipeline_job, daily_mysql_ingest_job, daily_hubspot_ingest_job, daily_dbt_job],
    schedules=[daily_mysql_3am_schedule, daily_hubspot_230am_schedule, daily_dbt_4am_schedule],
    resources={
        "dbt": DbtCliResource(project_dir="/dbt"),
    },
)
