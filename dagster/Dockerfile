FROM python:3.11-slim

# Install system deps for psycopg2 + mysqlclient
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Pin all Python deps for reproducible builds
RUN pip install --no-cache-dir \
    dagster==1.9.10 \
    dagster-webserver==1.9.10 \
    dagster-postgres==0.25.10 \
    dagster-dbt==0.25.10 \
    dbt-core==1.9.4 \
    dbt-postgres==1.9.1 \
    pymysql==1.1.1 \
    pandas==2.2.3 \
    sqlalchemy==2.0.36 \
    hubspot-api-client==9.0.0 \
    dbt-metabase==1.8.5

WORKDIR /app

# Copy Dagster project code
COPY project/ /app/project/

# Copy entrypoint script (used only by dagster_user_code service)
COPY entrypoint_code_server.sh /app/entrypoint_code_server.sh
RUN chmod +x /app/entrypoint_code_server.sh

# Bake config files directly into DAGSTER_HOME so all three services
# (user_code, webserver, daemon) find them without bind-mount ordering issues.
# Env vars in dagster.yaml (DAGSTER_PG_*) are still resolved at runtime from docker-compose.
ENV DAGSTER_HOME=/var/lib/dagster
RUN mkdir -p /var/lib/dagster
COPY dagster.yaml /var/lib/dagster/dagster.yaml
COPY workspace.yaml /var/lib/dagster/workspace.yaml

EXPOSE 4000
