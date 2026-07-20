-- stg_hubspot_owners: CRM owners (sales reps / account managers).
--
-- Joined to companies and deals via owner_id to attribute pipeline to people.

with source as (

    select * from {{ source('hubspot', 'hubspot_owner') }}

)

select
    id                                              as owner_id,
    email                                           as owner_email,
    trim(coalesce(first_name, '') || ' ' || coalesce(last_name, '')) as owner_name,
    nullif(created_at, '')::timestamp               as created_at,
    nullif(updated_at, '')::timestamp               as updated_at

from source
