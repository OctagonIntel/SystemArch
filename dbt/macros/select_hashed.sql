{#
  ADR-005. Selects every column of `relation`, swapping each column that
  policy/access.yaml classifies above public for governance.pii_hash(column).
  The classification is read from governance.column_classification at run time,
  so the policy file stays the only place it's written down.
#}
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
