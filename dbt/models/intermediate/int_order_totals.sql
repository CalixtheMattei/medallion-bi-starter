-- int_order_totals: one row per order with its item totals.
--
-- Intermediate layer: reusable join between orders and their line items,
-- consumed by both marts. Not synced to Metabase (see _METABASE_EXCLUDE_MODELS
-- in dagster/project/assets.py) — end users query the marts instead.

with orders as (

    select * from {{ ref('stg_shop_orders') }}

),

items as (

    select
        order_id,
        sum(quantity)      as total_units,
        sum(line_total)    as order_total

    from {{ ref('stg_shop_order_items') }}
    group by order_id

)

select
    orders.order_id,
    orders.customer_id,
    orders.ordered_at,
    orders.status,
    orders.is_revenue,
    coalesce(items.total_units, 0)  as total_units,
    coalesce(items.order_total, 0)  as order_total

from orders
left join items using (order_id)
