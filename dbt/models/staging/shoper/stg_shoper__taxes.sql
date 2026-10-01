-- One row per tax rate definition. Lookup table for products.tax_id.

with source as (

    select * from {{ source('shoper', 'taxes') }}

),

renamed as (

    select
        tax_id,
        store_id,
        value as tax_rate_pct,
        name  as tax_name,
        tax_class,

        loaded_at

    from source

)

select * from renamed
