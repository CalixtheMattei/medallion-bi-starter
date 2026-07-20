# Mart Reference

Plain-English reference for every gold-layer mart in the demo stack — written for whoever is building a dashboard, not for the engineer who wrote the SQL. Each mart is one query away from a Metabase question; the descriptions below are also synced into Metabase automatically after every dbt build.

---

## `mart_customer_activity`

**One row per customer.** Answers: who's active, who's slowing down, who's gone dark, and who never ordered at all.

| Column | What it means |
|---|---|
| `activity_status` | `active` (ordered in the last 30 days) · `slowing` (31–90 days) · `dormant` (90+ days) · `never_ordered` |
| `lifetime_revenue` | Sum of all **paid or shipped** orders — pending/cancelled orders never count |
| `lifetime_orders` | Count of those same revenue-generating orders |
| `first_order_at` / `last_order_at` | First and most recent revenue-generating order |

**Good dashboard questions:** "How many customers are dormant, by country?" · "Who are our top 20 customers by lifetime revenue?" · "What share of customers have never converted?"

**Caveat:** the 30/90-day thresholds are defined once, in `dbt_project.yml` (`activity_active_days`, `activity_slowing_days`) — check there before comparing this mart across time periods, since changing the var changes every customer's bucket retroactively on the next `dbt build`.

---

## `mart_revenue_monthly`

**One row per month × product category.** Answers: how is revenue trending, and which categories drive it?

| Column | What it means |
|---|---|
| `revenue` | Sum of line totals at **purchase-time price** (`unit_price_cents` on the order item), not the product's current catalog price |
| `orders` | Distinct revenue-generating orders in that month/category |
| `avg_order_value` | `revenue / orders` |

**Good dashboard questions:** "Which category grew fastest last quarter?" · "What's our average order value trend?"

**Caveat:** only paid or shipped orders count (same `is_revenue` definition as `mart_customer_activity` — the two marts will never disagree on what counts as revenue).

---

## Adding your own mart

When you build a new mart (by hand or via the `adapt-query` skill):
1. Add its description and column docs to `dbt/models/marts/schema.yml` — that's what Metabase shows.
2. Add an entry to this file, in the same three-part shape: what question it answers, what each non-obvious column means, and one caveat a dashboard builder needs before trusting a number.
