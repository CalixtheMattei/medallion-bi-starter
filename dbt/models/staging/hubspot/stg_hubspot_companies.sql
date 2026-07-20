-- stg_hubspot_companies: standard HubSpot company properties, typed.
--
-- The raw extract lands EVERY property your portal exposes (all as text).
-- This model deliberately selects only standard properties so it works on any
-- HubSpot portal. Add your portal's custom properties here as needed —
-- rename their machine names to readable snake_case in the process.

with source as (

    select * from {{ source('hubspot', 'hubspot_company') }}

)

select
    hs_object_id                                    as company_id,
    name                                            as company_name,
    domain,
    industry,
    city,
    country,

    lifecyclestage                                  as lifecycle_stage,
    nullif(numberofemployees, '')::numeric          as employee_count,
    nullif(annualrevenue, '')::numeric              as annual_revenue,

    hubspot_owner_id                                as owner_id,

    nullif(createdate, '')::timestamp               as created_at,
    nullif(hs_lastmodifieddate, '')::timestamp      as updated_at

from source
