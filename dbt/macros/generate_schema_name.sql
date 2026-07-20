-- Override dbt's default schema naming behavior.
--
-- By default dbt generates: {target.schema}_{custom_schema}
-- e.g. profile default "analytics" + model/source config "+schema: raw" → "analytics_raw"
--
-- This macro makes dbt use the custom schema name AS-IS when one is set,
-- so dbt can target "raw" or "analytics" exactly as configured.
--
-- Reference: https://docs.getdbt.com/docs/build/custom-schemas

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
