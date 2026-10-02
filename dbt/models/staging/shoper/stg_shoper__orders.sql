-- Staging model for Shoper orders: one row per order, same grain as raw_orders.
-- Staging does exactly three things - rename, cast, clean - and nothing else. No joins, no
-- aggregation, no business rules. Everything downstream reads this instead of raw_orders, so
-- the "dates are strings" and "'0000-00-00' means null" quirks get fixed here, once.

with source as (

    -- source() instead of a hardcoded table name: dbt resolves it to "public"."raw_orders"
    -- and records the edge raw_orders -> stg_shoper__orders in the lineage graph.
    select * from {{ source('shoper', 'orders') }}

),

renamed as (

    select
        -- ids
        order_id,
        store_id,
        user_id as customer_id,
        status_id,
        payment_id,
        shipping_id,
        currency_id,

        -- timestamps: the API sends strings, sometimes '' or '0000-00-00 00:00:00'
        {{ safe_timestamp('date') }}          as ordered_at,
        {{ safe_timestamp('status_date') }}   as status_changed_at,
        {{ safe_timestamp('confirm_date') }}  as confirmed_at,
        {{ safe_timestamp('delivery_date') }} as delivery_at,

        -- money
        sum            as order_total,
        paid           as amount_paid,
        shipping_cost,
        currency_rate,

        -- discounts are percentages in the API, not amounts
        discount_client as discount_client_pct,
        discount_group  as discount_group_pct,
        discount_levels as discount_levels_pct,
        discount_code   as discount_code_pct,

        -- flags
        coalesce(is_paid, false) as is_paid,
        coalesce(confirm, false) as is_confirmed,

        -- attributes
        lower(nullif(btrim(email), '')) as customer_email,
        code                            as order_code,
        nullif(btrim(promo_code), '')   as promo_code,
        total_products                  as items_count,
        origin                          as origin_code,

        -- ETL metadata
        loaded_at

    from source

)

select * from renamed
