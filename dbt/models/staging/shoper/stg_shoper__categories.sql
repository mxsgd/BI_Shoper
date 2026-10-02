-- One row per product category. The tree is self-referencing: parent_category_id points at
-- another category_id in this same model (NULL for top-level categories).

with source as (

    select * from {{ source('shoper', 'categories') }}

),

renamed as (

    select
        category_id,
        store_id,
        (translations ->> '_parent_id')::bigint as parent_category_id,

        coalesce(
            translations -> 'pl_PL' ->> 'name',
            translations -> 'en_GB' ->> 'name'
        )                     as category_name,
        coalesce(root, false) as is_root,
        "order"               as sort_order,  -- quoted: order is a SQL keyword

        loaded_at

    from source

)

select * from renamed
