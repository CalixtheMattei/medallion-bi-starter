-- stg_hubspot_deals: standard HubSpot deal properties, typed.
--
-- `deal_stage` is HubSpot's internal stage ID — human-readable labels are
-- resolved in mart_hubspot_pipeline via the hubspot_pipeline_stage_labels seed.
-- Edit that seed to match your portal's pipelines.

with source as (

    select * from {{ source('hubspot', 'hubspot_deal') }}

)

select
    hs_object_id                                    as deal_id,
    dealname                                        as deal_name,
    dealstage                                       as deal_stage,
    pipeline                                        as pipeline_id,
    dealtype                                        as deal_type,

    nullif(amount, '')::numeric                     as amount,
    nullif(amount_in_home_currency, '')::numeric    as amount_home_currency,

    hubspot_owner_id                                as owner_id,

    nullif(closedate, '')::date                     as close_date,
    nullif(createdate, '')::timestamp               as created_at,
    nullif(hs_lastmodifieddate, '')::timestamp      as updated_at

from source
