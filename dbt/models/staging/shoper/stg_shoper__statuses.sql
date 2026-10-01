-- One row per order status definition (id -> display name). Lookup table for orders.status_id.

with source as (

    select * from {{ source('shoper', 'statuses') }}

),

renamed as (

    select
        status_id,
        store_id,
        coalesce(
            nullif(btrim(name), ''),
            translations -> 'pl_PL' ->> 'name'
        )    as status_name,
        type as status_type_code,

        loaded_at

    from source

)

select * from renamed
