-- stg_shop_products: clean and normalise the product catalog.
--
-- Converts integer cents (raw OLTP convention) to decimal currency units.
-- Downstream models should always use `current_price`, never re-derive from cents.

with source as (

    select * from {{ source('shop', 'shop_products') }}

),

cleaned as (

    select
        id                                          as product_id,
        name                                        as product_name,
        category,
        round(price_cents / 100.0, 2)               as current_price,
        date_created::timestamp                     as created_at

    from source

)

select * from cleaned
