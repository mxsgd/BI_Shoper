-- One row per producer (brand/manufacturer). Lookup table for products.producer_id.

with source as (

    select * from {{ source('shoper', 'producers') }}

),

renamed as (

    select
        producer_id,
        store_id,
        nullif(btrim(name), '') as producer_name,
        nullif(btrim(web), '')  as website_url,
        coalesce(isdefault, false) as is_default,

        loaded_at

    from source

)

select * from renamed
