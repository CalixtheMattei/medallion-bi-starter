"""
Headlessly complete Metabase's first-run setup and connect the `warehouse`
Postgres database — no browser required.

This is the one step in the "plug-and-play" flow that otherwise means clicking
through Metabase's setup wizard by hand. Reads credentials straight from `.env`
(no need to `export`/`source` anything first). Idempotent — safe to re-run
against an already-provisioned instance; it only fills in what's missing.

Self-healing: if METABASE_PASSWORD fails Metabase's own password-strength check
(this has already happened once with the shipped placeholder — Metabase's setup
endpoint is stricter than its regular user-creation endpoint, and stricter than
whatever "looks reasonable" by eye), this script generates a replacement,
completes setup with it, and writes it back into `.env` so subsequent runs and
`dbt-metabase` stay in sync.

Usage:
  python3 scripts/bootstrap_metabase.py
"""

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

ENV_PATH = os.environ.get("ENV_FILE", ".env")


def load_dotenv(path):
    """Populate missing os.environ entries from a .env file. Real env vars win."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv(ENV_PATH)

BASE = os.environ.get("METABASE_URL", f"http://localhost:{os.environ.get('METABASE_PORT', '3000')}")
DB_NAME = os.environ.get("METABASE_DATABASE_NAME", "warehouse")
PG_HOST = os.environ.get("METABASE_PG_HOST", "postgres")  # hostname on the compose network, not the host machine
PG_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
PG_USER = os.environ.get("POSTGRES_USER", "postgres")
PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")


def api(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Metabase-Session"] = token
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        body = urllib.request.urlopen(req).read()
        return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return {"_error": True, "_status": e.code, **json.loads(raw)}
        except json.JSONDecodeError:
            return {"_error": True, "_status": e.code, "_raw": raw}


def wait_for_health(timeout=180):
    print("Waiting for Metabase...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE}/api/health", timeout=3)
            print("  Metabase is up.")
            return
        except Exception:
            time.sleep(3)
    print(f"Metabase did not come up within {timeout}s at {BASE}.", file=sys.stderr)
    sys.exit(1)


def persist_env_password(new_password):
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH) as f:
        lines = f.readlines()
    with open(ENV_PATH, "w") as f:
        for line in lines:
            f.write(f"METABASE_PASSWORD={new_password}\n" if line.startswith("METABASE_PASSWORD=") else line)
    os.environ["METABASE_PASSWORD"] = new_password


def run_setup(token_val, user, password):
    return api("POST", "/api/setup", {
        "token": token_val,
        "user": {"first_name": "Admin", "last_name": "User", "email": user, "password": password},
        "prefs": {"site_name": "Medallion BI Starter", "allow_tracking": False},
    })


def ensure_admin_account():
    user = os.environ["METABASE_USER"]
    password = os.environ["METABASE_PASSWORD"]

    props = api("GET", "/api/session/properties")

    if not props.get("has-user-setup"):
        print(f"Running first-time setup for {user}...")
        resp = run_setup(props["setup-token"], user, password)

        if resp.get("_error"):
            print(f"  METABASE_PASSWORD rejected by Metabase ({resp.get('errors', resp)}) — generating a new one.")
            password = secrets.token_urlsafe(18) + "-A1!"
            resp = run_setup(props["setup-token"], user, password)
            if resp.get("_error"):
                print(f"Setup failed even with a generated password: {resp}", file=sys.stderr)
                sys.exit(1)
            persist_env_password(password)
            print(f"  New METABASE_PASSWORD written to {ENV_PATH}.")
            print("  If dagster containers are running, restart them to pick it up:")
            print("    docker compose up -d dagster_user_code dagster_webserver dagster_daemon")

        print(f"  Admin account created: {user}")
        return resp["id"]

    # Already set up on a prior run — verify .env still matches the real account.
    resp = api("POST", "/api/session", {"username": user, "password": password})
    if resp.get("_error"):
        print(
            f"Metabase is already set up, but METABASE_USER/METABASE_PASSWORD in {ENV_PATH} don't "
            "match its stored admin account (e.g. the password was changed by hand since). Update "
            f"{ENV_PATH} to the real credentials and re-run, or drop the `metabase` Postgres database "
            "to reset Metabase from scratch:\n"
            '    docker compose exec -T postgres psql -U postgres -d postgres -c '
            '"DROP DATABASE metabase WITH (FORCE); CREATE DATABASE metabase;"\n'
            "    docker compose restart metabase",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"  Admin account already set up as {user}.")
    return resp["id"]


def ensure_warehouse_database(token):
    databases = api("GET", "/api/database", token=token).get("data", [])
    existing = next((d for d in databases if d["name"] == DB_NAME), None)
    if existing:
        print(f"  '{DB_NAME}' database already connected in Metabase (id={existing['id']}).")
        return existing["id"]

    print(f"Connecting the '{DB_NAME}' Postgres database...")
    resp = api("POST", "/api/database", token=token, payload={
        "engine": "postgres",
        "name": DB_NAME,
        "details": {
            "host": PG_HOST,
            "port": PG_PORT,
            "dbname": DB_NAME,
            "user": PG_USER,
            "password": PG_PASSWORD,
            "schema-filters-type": "inclusion",
            "schema-filters-patterns": "analytics",
        },
        "is_full_sync": True,
    })
    if resp.get("_error"):
        print(f"Failed to connect '{DB_NAME}': {resp}", file=sys.stderr)
        sys.exit(1)
    db_id = resp["id"]

    print("  Waiting for initial sync...")
    for _ in range(20):
        status = api("GET", f"/api/database/{db_id}", token=token).get("initial_sync_status")
        if status == "complete":
            break
        time.sleep(3)
    print(f"  '{DB_NAME}' connected (id={db_id}).")
    return db_id


if __name__ == "__main__":
    wait_for_health()
    session_token = ensure_admin_account()
    ensure_warehouse_database(session_token)
    print(f"\nMetabase is ready: {BASE}")
