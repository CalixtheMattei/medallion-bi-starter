-- stg_shop_orders: clean and normalise raw order headers.
--
-- Decodes the raw integer status code into a readable label:
--   0 = pending · 1 = paid · 2 = shipped · 3 = cancelled
--
-- Exposes `is_revenue` so downstream models share one definition of
-- "this order counts as revenue" (paid or shipped, not pending/cancelled).

with source as (

    select * from {{ source('shop', 'shop_orders') }}

),

cleaned as (

    select
        id                                          as order_id,
        customer_id,
        date_created::timestamp                     as ordered_at,

        -- Readable status from the raw integer code
        case status
            when 0 then 'pending'
            when 1 then 'paid'
            when 2 then 'shipped'
            when 3 then 'cancelled'
            else        'unknown'
        end                                         as status,

        -- Single shared definition of a revenue-generating order
        (status in (1, 2))                          as is_revenue

    from source

)

select * from cleaned
