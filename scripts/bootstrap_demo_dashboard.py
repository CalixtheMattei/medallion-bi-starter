"""
Bootstrap a friendly "Welcome" dashboard from the two demo marts.

Meant to be the first thing a new user sees in Metabase after running the
stack: a short welcome note, three real charts built from the synthetic
e-commerce data, and a small easter egg for anyone paying close attention.
Entirely optional — the stack works fine without it. Idempotent: re-running
finds and skips a dashboard that already has the welcome marker.

Usage:
  1. Finish the Metabase setup wizard and add the `warehouse` Postgres database
     (see README "Quick start" / the `setup` agent skill).
  2. Run `dbt build` at least once so mart_customer_activity and
     mart_revenue_monthly exist and have rows.
  3. METABASE_USER / METABASE_PASSWORD must be set in the environment (.env).
  4. python3 scripts/bootstrap_demo_dashboard.py
"""

import os
import sys
import time
import urllib.error
import urllib.request
import json

BASE   = os.environ.get("METABASE_URL", "http://localhost:3000")
MARKER = "<!-- welcome-dashboard-v1 -->"


def api(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Metabase-Session"] = token
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        print(f"  ERR {e.code} {method} {path}: {e.read().decode()[:300]}", file=sys.stderr)
        return None


def find_table(tables, name):
    for t in tables:
        if t["name"] == name:
            return t
    return None


def field_id(fields, name):
    for f in fields:
        if f["name"] == name:
            return f["id"]
    raise KeyError(f"field '{name}' not found — has `dbt build` run since the last schema change?")


user     = os.environ["METABASE_USER"]
password = os.environ["METABASE_PASSWORD"]
token = api("POST", "/api/session", {"username": user, "password": password})["id"]

# ── Find the warehouse database and the two demo marts ───────────────────────

databases = api("GET", "/api/database", token=token)["data"]
db = next((d for d in databases if d["name"] == "warehouse"), None)
if not db:
    print("Could not find a 'warehouse' database in Metabase — add it via the setup "
          "wizard first (Postgres, host=postgres, db=warehouse, schema=analytics).", file=sys.stderr)
    sys.exit(1)
db_id = db["id"]

api("POST", f"/api/database/{db_id}/sync_schema", token=token)
time.sleep(5)

metadata = api("GET", f"/api/database/{db_id}/metadata", token=token)
tables = metadata.get("tables", [])

activity_table = find_table(tables, "mart_customer_activity")
revenue_table  = find_table(tables, "mart_revenue_monthly")
if not activity_table or not revenue_table:
    print("mart_customer_activity / mart_revenue_monthly not found in Metabase yet — "
          "run `dbt build` first, then re-run this script.", file=sys.stderr)
    sys.exit(1)

activity_fields = api("GET", f"/api/table/{activity_table['id']}/query_metadata", token=token)["fields"]
revenue_fields  = api("GET", f"/api/table/{revenue_table['id']}/query_metadata", token=token)["fields"]

# ── Build the three questions ─────────────────────────────────────────────────

print("Creating questions…")

q_status = api("POST", "/api/card", token=token, payload={
    "name": "Customers by Activity Status",
    "display": "bar",
    "visualization_settings": {
        "graph.dimensions": ["activity_status"],
        "graph.metrics": ["count"],
    },
    "dataset_query": {
        "type": "query",
        "database": db_id,
        "query": {
            "source-table": activity_table["id"],
            "aggregation": [["count"]],
            "breakout": [["field", field_id(activity_fields, "activity_status"), {"base-type": "type/Text"}]],
            "order-by": [["desc", ["aggregation", 0]]],
        },
    },
})

q_revenue = api("POST", "/api/card", token=token, payload={
    "name": "Revenue by Month",
    "display": "line",
    "visualization_settings": {
        "graph.dimensions": ["order_month"],
        "graph.metrics": ["revenue"],
    },
    "dataset_query": {
        "type": "query",
        "database": db_id,
        "query": {
            "source-table": revenue_table["id"],
            "aggregation": [["sum", ["field", field_id(revenue_fields, "revenue"), {"base-type": "type/Float"}]]],
            "breakout": [["field", field_id(revenue_fields, "order_month"), {"base-type": "type/DateTime", "temporal-unit": "month"}]],
            "order-by": [["asc", ["breakout", 0]]],
        },
    },
})

q_top_customers = api("POST", "/api/card", token=token, payload={
    "name": "Top 10 Customers by Lifetime Revenue",
    "display": "table",
    "visualization_settings": {},
    "dataset_query": {
        "type": "query",
        "database": db_id,
        "query": {
            "source-table": activity_table["id"],
            "order-by": [["desc", ["field", field_id(activity_fields, "lifetime_revenue"), {"base-type": "type/Float"}]]],
            "limit": 10,
        },
    },
})

cards = [c for c in (q_status, q_revenue, q_top_customers) if c]
if len(cards) < 3:
    print("One or more questions failed to create — check the errors above.", file=sys.stderr)
    sys.exit(1)

# ── Assemble the welcome dashboard ────────────────────────────────────────────

WELCOME_TEXT = f"""{MARKER}
# 👋 Welcome to the Medallion BI Starter

You're looking at real charts, built from real (synthetic) data, that ran through the
full pipeline: **MySQL → Dagster → Postgres (raw) → dbt (staging → marts) → this dashboard.**
Nobody hand-typed these numbers — `dbt build` computed them, and `dbt-metabase` synced
every table and column description you see in this instance automatically.

A few things worth trying next:
- Click into any chart below and hit **"Explore results"** to slice it yourself
- Open a table (e.g. `mart_customer_activity`) and check the field descriptions —
  they came straight from `dbt/models/marts/schema.yml`
- Ask your AI coding agent to run the `create-dashboard` skill to build one of these
  from scratch, or `adapt-query` to turn a SQL query of your own into a governed model

Check `docs/MART_REFERENCE.md` for what each mart actually means, and `docs/ARCHITECTURE.md`
for how the whole thing fits together — including a couple of hard-won lessons about
scheduling that are easy to get wrong the first time.

*Enjoy the tour. And yes, someone really did sit down and generate 80 fake customers
and 300-odd fake orders just so this dashboard would have something to show you —
check the product catalog if you want proof that whoever built this had a sense of humor. 🦆*
"""

print("\nCreating dashboard…")
existing_dashboards = api("GET", "/api/dashboard", token=token) or []
already = next((d for d in existing_dashboards
                if MARKER in (d.get("description") or "")), None)

dashboard = api("POST", "/api/dashboard", token=token, payload={
    "name": "👋 Welcome",
    "description": MARKER,
}) if not already else already

if not dashboard:
    print("Failed to create the dashboard — see errors above.", file=sys.stderr)
    sys.exit(1)

dash_id = dashboard["id"]

dashcards = [
    {
        "id": -1, "card_id": None, "row": 0, "col": 0, "size_x": 24, "size_y": 6,
        "visualization_settings": {
            "text": WELCOME_TEXT,
            "virtual_card": {"name": None, "display": "text", "visualization_settings": {}, "dataset_query": {}, "archived": False},
        },
        "parameter_mappings": [],
    },
    {"id": -2, "card_id": cards[0]["id"], "row": 6, "col": 0,  "size_x": 12, "size_y": 8, "parameter_mappings": []},
    {"id": -3, "card_id": cards[1]["id"], "row": 6, "col": 12, "size_x": 12, "size_y": 8, "parameter_mappings": []},
    {"id": -4, "card_id": cards[2]["id"], "row": 14, "col": 0, "size_x": 24, "size_y": 8, "parameter_mappings": []},
]

result = api("PUT", f"/api/dashboard/{dash_id}", token=token, payload={"dashcards": dashcards})
if result:
    print(f"\n✓ Welcome dashboard ready: {BASE}/dashboard/{dash_id}")
else:
    print("Failed to assemble the dashboard — see errors above.", file=sys.stderr)
    sys.exit(1)
