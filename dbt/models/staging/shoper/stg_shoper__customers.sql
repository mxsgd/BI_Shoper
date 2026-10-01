-- One row per registered customer (Shoper "user"). Guest orders have no row here -
-- they only exist as an email on stg_shoper__orders.

with source as (

    select * from {{ source('shoper', 'customers') }}

),

renamed as (

    select
        -- ids
        user_id as customer_id,
        store_id,
        group_id as customer_group_id,

        -- attributes
        lower(nullif(btrim(email), '')) as customer_email,  -- same cleaning as orders, so they join
        nullif(btrim(firstname), '')    as first_name,
        nullif(btrim(lastname), '')     as last_name,
        discount                        as discount_pct,
        coalesce(active, false)         as is_active,
        origin                          as origin_code,

        -- timestamps
        {{ safe_timestamp('date_add') }}  as registered_at,
        {{ safe_timestamp('lastvisit') }} as last_visit_at,

        -- ETL metadata
        loaded_at

    from source

)

select * from renamed
