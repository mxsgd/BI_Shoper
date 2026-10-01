-- Staging model for Shoper order lines: one row per product line in an order, same grain as
-- raw_order_items. Rename and clean only - joining to orders/products happens in marts.

with source as (

    select * from {{ source('shoper', 'order_items') }}

),

renamed as (

    select
        -- ids
        order_id,
        store_id,
        order_item_id,
        product_id,
        stock_id,

        -- money
        price,
        discount_perc as discount_pct,
        tax as tax_label,
        tax_value as tax_rate_pct,

        -- attributes
        quantity,
        name as product_name,
        code as product_code,
        unit,

        -- ETL metadata
        loaded_at,
        updated_at

    from source

)

select * from renamed
