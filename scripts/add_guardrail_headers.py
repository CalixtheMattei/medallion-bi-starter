"""
Add a standardized "guardrail" text card at the top of Metabase dashboards.

A guardrail card tells the reader where the data comes from, how fresh it is,
and what caveats apply BEFORE they draw conclusions — the cheapest possible
piece of data governance. Shifts all existing cards down to make room.
Idempotent: skips dashboards that already have one (detected by marker text).

Usage:
  1. Edit GUARDRAILS below — one entry per dashboard ID, with the caveat text.
  2. METABASE_USER / METABASE_PASSWORD must be set in the environment (.env).
  3. python3 scripts/add_guardrail_headers.py
"""

import os
import urllib.request, json, sys

BASE   = os.environ.get("METABASE_URL", "http://localhost:3000")
MARKER = "<!-- guardrail-header-v1 -->"


def api(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Metabase-Session"] = token
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        print(f"  ERR {e.code} {method} {path}: {e.read().decode()[:200]}", file=sys.stderr)
        return None


user     = os.environ["METABASE_USER"]
password = os.environ["METABASE_PASSWORD"]
token = api("POST", "/api/session", {"username": user, "password": password})["id"]

# ── Guardrail text per dashboard ──────────────────────────────────────────────
# Keyed by Metabase dashboard ID (visible in the dashboard URL).
# The example below fits the demo Customer Activity dashboard — adapt the text
# to each dashboard you ship. A good guardrail answers three questions:
#   1. Which source(s) feed this dashboard?
#   2. When was the data last refreshed?
#   3. What must the reader know before trusting a number?

GUARDRAILS = {
    1: {
        "height": 3,
        "text": f"""{MARKER}
### 📊 Data Source & Freshness — Customer Activity

**Source:** e-commerce OLTP (demo) · **Updated:** daily ~04:00 UTC (extract at 03:00 UTC)

⚠ **Important caveats before drawing conclusions:**
- **lifetime_revenue** counts only paid or shipped orders — pending and cancelled orders are excluded.
- **activity_status** thresholds (30/90 days) are defined in dbt vars — check `dbt_project.yml` before comparing periods.
- Soft-deleted customers are excluded at the staging layer and never appear here.
""",
    },
}

# ── Apply to each dashboard ───────────────────────────────────────────────────

for dash_id, cfg in GUARDRAILS.items():
    print(f"\n── Dashboard {dash_id} ──────────────────────────")
    dash = api("GET", f"/api/dashboard/{dash_id}", token=token)
    if not dash:
        print("  Could not fetch dashboard — skipping.")
        continue

    existing = dash.get("dashcards", [])

    # Idempotency: skip if marker already present
    for card in existing:
        vs = card.get("visualization_settings", {})
        if MARKER in vs.get("text", ""):
            print("  Guardrail header already present — skipping.")
            break
    else:
        header_height = cfg["height"]

        # Shift all existing cards down
        shifted = []
        uid = -1
        for c in existing:
            shifted.append({**c, "row": c["row"] + header_height, "id": uid})
            uid -= 1

        # Build the text (guardrail) card
        header_card = {
            "id": uid,
            "card_id": None,
            "row": 0,
            "col": 0,
            "size_x": 24,
            "size_y": header_height,
            "visualization_settings": {
                "text": cfg["text"],
                "virtual_card": {
                    "name": None,
                    "display": "text",
                    "visualization_settings": {},
                    "dataset_query": {},
                    "archived": False,
                },
            },
            "parameter_mappings": [],
        }

        result = api("PUT", f"/api/dashboard/{dash_id}",
                     {"dashcards": [header_card] + shifted}, token)
        if result:
            print(f"  ✓ Guardrail header added ({len(result.get('dashcards',[]))} total cards)")
        else:
            print("  ✗ Failed to update dashboard")

print("\nDone.")
