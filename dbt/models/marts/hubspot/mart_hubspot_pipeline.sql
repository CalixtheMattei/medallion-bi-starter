-- mart_hubspot_pipeline: one row per deal with resolved stage labels and owner.
--
-- Business questions answered:
--   - How much pipeline is open, by stage?
--   - Win rate per owner / per pipeline?
--
-- Demonstrates the seed-join pattern: HubSpot stores stage IDs, the
-- hubspot_pipeline_stage_labels seed maps them to labels. Deals whose stage
-- is missing from the seed keep the raw ID (visible signal to update the seed).

{{ config(materialized='table') }}

with deals as (

    select * from {{ ref('stg_hubspot_deals') }}

),

stage_labels as (

    select * from {{ ref('hubspot_pipeline_stage_labels') }}

),

owners as (

    select * from {{ ref('stg_hubspot_owners') }}

)

select
    deals.deal_id,
    deals.deal_name,
    deals.deal_type,

    coalesce(stage_labels.pipeline_label, deals.pipeline_id)  as pipeline,
    coalesce(stage_labels.stage_label, deals.deal_stage)      as stage,
    coalesce(stage_labels.stage_category, 'Unknown')          as stage_category,
    stage_labels.stage_order,

    deals.amount,
    deals.amount_home_currency,

    owners.owner_name,
    owners.owner_email,

    deals.close_date,
    deals.created_at,
    deals.updated_at

from deals
left join stage_labels
    on  deals.pipeline_id = stage_labels.pipeline_id
    and deals.deal_stage  = stage_labels.stage_id
left join owners using (owner_id)
