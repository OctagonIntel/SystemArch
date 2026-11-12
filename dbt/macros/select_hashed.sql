{# ADR-005. Selects every column, hashing the ones classified above public. #}
{% macro select_hashed(relation, table_name) %}
{% if execute %}
    {% set classified = run_query(
        "select column_name from governance.column_classification where table_name = '" ~ table_name ~ "'"
    ).columns[0].values() %}
    {% set columns = adapter.get_columns_in_relation(relation) %}
select
{% for col in columns %}
    {% if col.name in classified -%}
    governance.pii_hash({{ adapter.quote(col.name) }}::text) as {{ adapter.quote(col.name) }}
    {%- else -%}
    {{ adapter.quote(col.name) }}
    {%- endif %}{{ "," if not loop.last }}
{% endfor %}
from {{ relation }}
{% else %}
select * from {{ relation }}
{% endif %}
{% endmacro %}
