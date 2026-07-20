import os
import subprocess
import time
from pathlib import Path

from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, dbt_assets

# dbt project is bind-mounted at /dbt in the dagster_user_code container.
# manifest.json is generated at container startup by entrypoint_code_server.sh (dbt parse).
DBT_MANIFEST = Path("/dbt/target/manifest.json")

# Intermediate models excluded from Metabase sync because they are internal
# join/aggregation layers not meant for end-user querying. Update this list
# whenever an intermediate model is added or removed.
_METABASE_EXCLUDE_MODELS = [
    "int_order_totals",
]


@dbt_assets(manifest=DBT_MANIFEST)
def dbt_project_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """All dbt models as Dagster assets.

    Runs `dbt build` (seeds → models → tests), then syncs model and column
    descriptions from dbt schema.yml → Metabase field metadata so the
    Metabase connector reads rich semantic context automatically.
    """
    yield from dbt.cli(["build"], context=context).stream()
    _sync_metabase_descriptions(context)


def _sync_metabase_descriptions(context: AssetExecutionContext) -> None:
    """Push dbt schema.yml descriptions → Metabase field metadata via dbt-metabase.

    Retries once on transient failures (e.g. Metabase rolling restart).
    Raises on persistent failure so the Dagster run is marked as failed.
    """
    url = os.environ.get("METABASE_URL", "http://metabase:3000")
    user = os.environ.get("METABASE_USER")
    password = os.environ.get("METABASE_PASSWORD")
    db_name = os.environ.get("METABASE_DATABASE_NAME", "warehouse")

    if not user or not password:
        context.log.warning("METABASE_USER / METABASE_PASSWORD not set — skipping Metabase sync.")
        return

    context.log.info(f"Syncing dbt descriptions -> Metabase ({url}, database='{db_name}')…")

    cmd = [
        "dbt-metabase", "models",
        "--manifest-path", str(DBT_MANIFEST),
        "--metabase-url", url,
        "--metabase-username", user,
        "--metabase-password", password,
        "--metabase-database", db_name,
        "--include-schemas", "analytics",
        "--sync-timeout", "0",
        "--exclude-models", ",".join(_METABASE_EXCLUDE_MODELS),
    ]

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            context.log.error(
                f"dbt-metabase sync timed out (attempt {attempt}/{max_attempts})"
            )
            if attempt < max_attempts:
                time.sleep(5)
                continue
            raise Exception("dbt-metabase sync timed out after all attempts") from None

        if result.stdout:
            context.log.info(result.stdout)
        if result.returncode == 0:
            context.log.info("Metabase field descriptions synced successfully.")
            return

        context.log.error(
            f"dbt-metabase sync failed (attempt {attempt}/{max_attempts}, "
            f"exit {result.returncode}):\n{result.stderr}"
        )
        if attempt < max_attempts:
            time.sleep(5)

    raise Exception(
        f"dbt-metabase sync failed after {max_attempts} attempts — "
        "check Metabase connectivity and the dbt-metabase logs above."
    )
