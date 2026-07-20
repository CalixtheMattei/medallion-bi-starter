-- mart_revenue_monthly: revenue per month × product category.
--
-- Business questions answered:
--   - How is revenue trending month over month?
--   - Which product categories drive it?
--   - What is the average order value per category?
--
-- Only revenue-generating orders are counted (paid or shipped — the shared
-- `is_revenue` definition from stg_shop_orders). Cancelled and pending
-- orders never appear here.

{{ config(materialized='table') }}

with revenue_items as (

    select
        date_trunc('month', orders.ordered_at)     as order_month,
        products.category,
        items.quantity,
        items.line_total,
        orders.order_id

    from {{ ref('stg_shop_order_items') }} items
    join {{ ref('stg_shop_orders') }} orders using (order_id)
    join {{ ref('stg_shop_products') }} products using (product_id)
    where orders.is_revenue

)

select
    order_month,
    category,
    count(distinct order_id)                       as orders,
    sum(quantity)                                  as units_sold,
    sum(line_total)                                as revenue,
    round(sum(line_total) / count(distinct order_id), 2) as avg_order_value

from revenue_items
group by order_month, category
order by order_month, category
