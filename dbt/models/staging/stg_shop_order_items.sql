-- stg_shop_order_items: clean and normalise order line items.
--
-- `unit_price` is the price at purchase time (may differ from the product's
-- current catalog price — discounts, price changes). Revenue calculations
-- must always use this, never stg_shop_products.current_price.

with source as (

    select * from {{ source('shop', 'shop_order_items') }}

),

cleaned as (

    select
        id                                          as order_item_id,
        order_id,
        product_id,
        quantity,
        round(unit_price_cents / 100.0, 2)          as unit_price,
        round(quantity * unit_price_cents / 100.0, 2) as line_total

    from source

)

select * from cleaned
