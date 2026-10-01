-- One row per product (per store). Pulls the display name and active flag out of the
-- translations JSON so nothing downstream has to know Shoper's nested shape.
-- Prices live per variant in stg_shoper__product_stocks, not here.

with source as (

    select * from {{ source('shoper', 'products') }}

),

renamed as (

    select
        -- ids
        product_id,
        store_id,
        producer_id,
        category_id,
        group_id,
        tax_id,
        currency_id,

        -- translations is {"pl_PL": {"name": ..., "active": 1}, "en_GB": {...}}.
        -- Polish first because Shoper stores are Polish; English as fallback.
        coalesce(
            translations -> 'pl_PL' ->> 'name',
            translations -> 'en_GB' ->> 'name'
        )                                               as product_name,
        (translations -> 'pl_PL' ->> 'active')::int = 1 as is_active,

        -- attributes
        nullif(btrim(code), '') as product_code,
        nullif(btrim(ean), '')  as ean,
        type = 1                as is_bundle,

        -- timestamps
        {{ safe_timestamp('add_date') }}  as created_at,
        {{ safe_timestamp('edit_date') }} as modified_at,

        -- ETL metadata
        loaded_at

    from source

)

select * from renamed
