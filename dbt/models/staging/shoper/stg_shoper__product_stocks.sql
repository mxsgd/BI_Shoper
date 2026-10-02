-- One row per product variant ("stock" in Shoper). Every product has exactly one base variant
-- (extended = false) that carries the product's main price; extra variants are extended = true.

with source as (

    select * from {{ source('shoper', 'product_stocks') }}

),

renamed as (

    select
        -- ids
        stock_id,
        product_id,
        store_id,
        availability_id,
        delivery_id,

        -- flags
        not coalesce(extended, false) as is_base_variant,
        coalesce(active, false)       as is_active,
        coalesce("default", false)    as is_default,  -- quoted: default is a SQL keyword

        -- prices
        price,
        price_wholesale,
        price_special,
        price_buying as cost_price,

        -- inventory
        stock      as stock_quantity,
        warn_level as stock_warn_level,
        sold       as sold_quantity,
        weight,

        -- attributes
        nullif(btrim(code), '') as variant_code,
        nullif(btrim(ean), '')  as ean,

        -- ETL metadata
        loaded_at

    from source

)

select * from renamed
