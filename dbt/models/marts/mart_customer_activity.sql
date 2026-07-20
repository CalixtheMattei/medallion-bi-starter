-- mart_customer_activity: one row per customer with order history and an
-- activity status — the "customer health" pattern.
--
-- Business questions answered:
--   - Which customers are active / slowing / dormant?
--   - Who are the top customers by lifetime revenue?
--   - How does activity break down by country?
--
-- Activity thresholds come from dbt vars (dbt_project.yml) so the definition
-- lives in exactly one place:
--   active   → last revenue order within activity_active_days
--   slowing  → within activity_slowing_days
--   dormant  → older than activity_slowing_days
--   never_ordered → no revenue order at all

{{ config(materialized='table') }}

with customers as (

    select * from {{ ref('stg_shop_customers') }}

),

order_history as (

    select
        customer_id,
        count(*)                                   as lifetime_orders,
        sum(order_total)                           as lifetime_revenue,
        min(ordered_at)                            as first_order_at,
        max(ordered_at)                            as last_order_at

    from {{ ref('int_order_totals') }}
    where is_revenue
    group by customer_id

)

select
    customers.customer_id,
    customers.customer_name,
    customers.country_code,
    customers.created_at                           as customer_since,

    coalesce(order_history.lifetime_orders, 0)     as lifetime_orders,
    coalesce(order_history.lifetime_revenue, 0)    as lifetime_revenue,
    order_history.first_order_at,
    order_history.last_order_at,

    case
        when order_history.last_order_at is null
            then 'never_ordered'
        when order_history.last_order_at >= current_date - interval '{{ var("activity_active_days") }} days'
            then 'active'
        when order_history.last_order_at >= current_date - interval '{{ var("activity_slowing_days") }} days'
            then 'slowing'
        else 'dormant'
    end                                            as activity_status

from customers
left join order_history using (customer_id)
