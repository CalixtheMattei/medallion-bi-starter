---
name: create-dashboard
description: Create a Metabase dashboard from a mart table using the Metabase REST API — creates questions (bar chart, breakdown, detail table), assembles them into a dashboard, and returns the URL. Use once a mart is built and synced to Metabase.
---

# create-dashboard

Create a Metabase dashboard for a mart table by calling the Metabase REST API.

## What you need from the user

1. **Mart table name** — e.g. `mart_customer_activity`
2. **The business question** — one sentence, e.g. "how many customers are active vs. dormant?"
3. **The category column** — the column to group/count by (e.g. `activity_status`, `category`)

Everything else (table ID, field IDs, database ID) is discovered via the API — no SQL required from the user.

## Stack context

- **Metabase URL**: `http://localhost:3000`
- **Credentials**: `.env` at repo root — `METABASE_USER` / `METABASE_PASSWORD`
- **Warehouse database**: confirm the ID via the API — do not assume it
- **All mart tables live in schema**: `analytics`
- **API version**: Metabase v0.50.x

## Instructions

### Step 1 — Authenticate

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/session \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$(grep METABASE_USER .env | cut -d= -f2)\",\"password\":\"$(grep METABASE_PASSWORD .env | cut -d= -f2)\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Token: $TOKEN"
```

### Step 2 — Find the database and table

```bash
curl -s -H "X-Metabase-Session: $TOKEN" http://localhost:3000/api/database | \
  python3 -c "import sys,json; [print(d['id'], d['name']) for d in json.load(sys.stdin).get('data',[])]"
```

If the target table is new, sync first:
```bash
curl -s -X POST "http://localhost:3000/api/database/<DB_ID>/sync_schema" -H "X-Metabase-Session: $TOKEN"
sleep 5
curl -s -H "X-Metabase-Session: $TOKEN" "http://localhost:3000/api/database/<DB_ID>/metadata" | \
  python3 -c "import sys,json; [print(t['id'], t['name']) for t in json.load(sys.stdin).get('tables',[])]"
```

### Step 3 — Get field IDs

```bash
curl -s -H "X-Metabase-Session: $TOKEN" "http://localhost:3000/api/table/<TABLE_ID>/query_metadata" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); [print(f['id'], f['name'], f['base_type']) for f in d.get('fields',[])]"
```

Note the field IDs for the dimension (category column), the metric, and any filter fields.

### Step 4 — Create questions

Use the structured query API (`"type": "query"`). Create 2–3 questions based on what the mart answers.

**Q1 — Bar chart: count per category (the headline chart)**
```bash
curl -s -X POST http://localhost:3000/api/card \
  -H "X-Metabase-Session: $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "<Mart name> — Count per <Category>",
    "display": "bar",
    "visualization_settings": {
      "graph.dimensions": ["<category_field_name>"],
      "graph.metrics": ["count"]
    },
    "dataset_query": {
      "type": "query",
      "database": <DB_ID>,
      "query": {
        "source-table": <TABLE_ID>,
        "aggregation": [["count"]],
        "breakout": [["field", <CATEGORY_FIELD_ID>, {"base-type": "<type/Text>"}]],
        "order-by": [["desc", ["aggregation", 0]]]
      }
    }
  }'
```

**Q2 — Detail table: raw rows for drill-down**
```bash
curl -s -X POST http://localhost:3000/api/card \
  -H "X-Metabase-Session: $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "<Mart name> — Detail",
    "display": "table",
    "visualization_settings": {},
    "dataset_query": {
      "type": "query",
      "database": <DB_ID>,
      "query": { "source-table": <TABLE_ID>, "limit": 500 }
    }
  }'
```

Adapt a third question (e.g. a numeric aggregate like sum/avg on a metric column) if the mart has one — e.g. `sum(lifetime_revenue)` per `activity_status`.

### Step 5 — Assemble the dashboard

```bash
curl -s -X POST http://localhost:3000/api/dashboard \
  -H "X-Metabase-Session: $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "<Dashboard name>"}'
```

Take the returned dashboard `id`, then add each card:
```bash
curl -s -X PUT "http://localhost:3000/api/dashboard/<DASH_ID>" \
  -H "X-Metabase-Session: $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "dashcards": [
      {"id": -1, "card_id": <Q1_CARD_ID>, "row": 0, "col": 0,  "size_x": 12, "size_y": 6, "parameter_mappings": []},
      {"id": -2, "card_id": <Q2_CARD_ID>, "row": 0, "col": 12, "size_x": 12, "size_y": 6, "parameter_mappings": []}
    ]
  }'
```

### Step 6 — Guardrail header (recommended)

Suggest (or run) `scripts/add_guardrail_headers.py` to stamp a data-source/freshness caveat card at the top of the new dashboard — see that script for the pattern. This is cheap governance: it tells anyone opening the dashboard where the data comes from and what to check before trusting a number.

### Step 7 — Report

Return the dashboard URL (`http://localhost:3000/dashboard/<DASH_ID>`), list the questions created, and note any caveats worth adding to `docs/MART_REFERENCE.md` for this mart.
