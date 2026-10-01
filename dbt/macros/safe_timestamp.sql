{#
    Casts a Shoper date string to timestamp, turning '' and '0000-00-00 ...' into NULL.
    Same rule as _sql_safe_timestamp() in backend/app/services/transform_service.py - a macro
    is dbt's way of writing that Python helper once and calling it from any model.
#}
{% macro safe_timestamp(column) %}
    case
        when {{ column }} is null or btrim({{ column }}::text) = '' then null
        when left(btrim({{ column }}::text), 4) = '0000' then null
        else {{ column }}::timestamp
    end
{% endmacro %}
