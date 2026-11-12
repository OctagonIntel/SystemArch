{# Use the schema names as written (staging, marts) instead of dbt's default staging_marts style. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.schema) | trim }}
{%- endmacro %}
