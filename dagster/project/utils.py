"""Shared utilities for Dagster assets."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def pg_engine() -> Engine:
    """Create a SQLAlchemy engine pointing at the warehouse Postgres database.

    Connection parameters are read from the DBT_POSTGRES_* environment variables
    injected by docker-compose.yml into the dagster_user_code container.
    """
    return create_engine(
        f"postgresql://{os.environ['DBT_POSTGRES_USER']}:{os.environ['DBT_POSTGRES_PASSWORD']}"
        f"@{os.environ['DBT_POSTGRES_HOST']}:{os.environ.get('DBT_POSTGRES_PORT', '5432')}"
        f"/{os.environ['DBT_POSTGRES_DBNAME']}"
    )
