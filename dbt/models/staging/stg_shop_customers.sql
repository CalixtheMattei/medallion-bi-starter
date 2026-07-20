-- stg_shop_customers: clean and normalise raw customer rows.
--
-- Staging responsibilities (and nothing more):
--   - rename raw columns to human-readable snake_case
--   - cast types (raw datetimes land as text/timestamp depending on the loader)
--   - decode raw flags into booleans
--   - drop soft-deleted rows (data hygiene, not business logic)
--
-- Business filters (country, activity status…) belong in the marts, never here.
-- Materialised as a VIEW: always reflects the latest raw load at zero storage cost.

with source as (

    select * from {{ source('shop', 'shop_customers') }}

),

cleaned as (

    select
        id                                          as customer_id,
        full_name                                   as customer_name,
        email,
        country                                     as country_code,
        date_created::timestamp                     as created_at

    from source
    where is_deleted = 0 or is_deleted is null

)

select * from cleaned
