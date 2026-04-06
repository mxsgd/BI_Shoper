"""Data quality check across RAW and CORE tables."""
from sqlalchemy import create_engine, text

DB_URL = "postgresql://postgres:2402@localhost:5432/bi_shoper"


def run():
    e = create_engine(DB_URL)
    with e.connect() as c:
        queries = {
            "RAW_PRODUCTS": """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE translations IS NULL) AS translations_null,
                    COUNT(*) FILTER (WHERE translations -> 'pl_PL' ->> 'name' IS NULL) AS name_pl_null,
                    COUNT(*) FILTER (WHERE category_id IS NULL) AS category_null,
                    COUNT(*) FILTER (WHERE stock IS NULL) AS stock_null,
                    COUNT(*) FILTER (WHERE (stock ->> 'price') IS NULL) AS price_null,
                    COUNT(*) FILTER (WHERE (stock ->> 'price')::numeric = 0) AS price_zero,
                    COUNT(*) FILTER (WHERE code IS NULL OR btrim(code) = '') AS code_empty,
                    COUNT(*) FILTER (WHERE ean IS NULL OR btrim(ean) = '') AS ean_empty,
                    COUNT(*) FILTER (WHERE categories IS NULL) AS cats_array_null
                FROM raw_products
            """,
            "RAW_CATEGORIES": """
                SELECT COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE translations IS NULL) AS trans_null,
                    COUNT(*) FILTER (WHERE translations -> 'pl_PL' ->> 'name' IS NULL) AS name_pl_null,
                    COUNT(*) FILTER (WHERE root IS NULL) AS root_null
                FROM raw_categories
            """,
            "RAW_DISCOUNTS": """
                SELECT COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE discount_type = 'promotion_code') AS promo_codes,
                    COUNT(*) FILTER (WHERE discount_type = 'special_offer') AS special_offers,
                    COUNT(*) FILTER (WHERE name IS NULL OR btrim(name) = '') AS name_empty
                FROM raw_discounts
            """,
            "FACT_ORDERS": """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE order_date IS NULL) AS date_null,
                    COUNT(*) FILTER (WHERE order_date = '1970-01-01'::timestamp) AS date_epoch,
                    COUNT(*) FILTER (WHERE customer_id IS NULL) AS customer_null,
                    COUNT(*) FILTER (WHERE gross_value IS NULL OR gross_value = 0) AS gross_zero,
                    COUNT(*) FILTER (WHERE order_status IS NULL OR btrim(order_status) = '') AS status_empty,
                    COUNT(*) FILTER (WHERE payment_status IS NULL) AS pay_status_null,
                    COUNT(*) FILTER (WHERE source_channel IS NULL OR source_channel = 'other') AS channel_other,
                    COUNT(*) FILTER (WHERE items_count = 0) AS items_zero,
                    COUNT(*) FILTER (WHERE discount_value > 0) AS has_discount,
                    COUNT(*) FILTER (WHERE payment_date IS NOT NULL) AS has_payment_date,
                    MIN(order_date) AS min_date,
                    MAX(order_date) AS max_date
                FROM fact_orders
            """,
            "FACT_ORDER_ITEMS": """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE product_id IS NULL) AS product_null,
                    COUNT(*) FILTER (WHERE category_id IS NULL) AS category_null,
                    COUNT(*) FILTER (WHERE unit_price_gross = 0) AS price_zero,
                    COUNT(*) FILTER (WHERE quantity = 0) AS qty_zero,
                    COUNT(*) FILTER (WHERE total_gross = 0) AS total_zero,
                    COUNT(*) FILTER (WHERE order_date IS NULL) AS date_null,
                    COUNT(*) FILTER (WHERE order_date = '1970-01-01'::timestamp) AS date_epoch
                FROM fact_order_items
            """,
            "DIM_PRODUCTS": """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE product_name IS NULL OR btrim(product_name) = '') AS name_empty,
                    COUNT(*) FILTER (WHERE product_name LIKE 'Product #%%') AS name_fallback,
                    COUNT(*) FILTER (WHERE category_id IS NULL) AS category_null,
                    COUNT(*) FILTER (WHERE retail_price IS NULL OR retail_price = 0) AS price_zero,
                    COUNT(*) FILTER (WHERE cost_price IS NULL) AS cost_null,
                    COUNT(*) FILTER (WHERE is_active IS NULL) AS active_null,
                    COUNT(*) FILTER (WHERE is_active = false) AS inactive
                FROM dim_products
            """,
            "DIM_CUSTOMERS": """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE total_orders = 0) AS no_orders,
                    COUNT(*) FILTER (WHERE total_revenue = 0) AS no_revenue,
                    COUNT(*) FILTER (WHERE first_order_date IS NULL) AS no_first_date,
                    COUNT(*) FILTER (WHERE customer_type IS NULL) AS type_null,
                    COUNT(*) FILTER (WHERE customer_type = 'new') AS type_new,
                    COUNT(*) FILTER (WHERE customer_type = 'returning') AS type_returning
                FROM dim_customers
            """,
            "DIM_CATEGORIES": """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE category_name IS NULL OR btrim(category_name) = '') AS name_empty,
                    COUNT(*) FILTER (WHERE category_name LIKE 'Category #%%') AS name_fallback
                FROM dim_categories
            """,
            "ORPHAN_CHECKS": """
                SELECT
                    (SELECT COUNT(*) FROM fact_order_items foi
                     LEFT JOIN fact_orders fo ON fo.order_id = foi.order_id
                     WHERE fo.order_id IS NULL) AS orphan_items,
                    (SELECT COUNT(*) FROM fact_orders fo
                     LEFT JOIN dim_customers dc ON dc.customer_id = fo.customer_id
                     WHERE fo.customer_id IS NOT NULL AND dc.customer_id IS NULL) AS orphan_customer_ref,
                    (SELECT COUNT(*) FROM fact_order_items foi
                     LEFT JOIN dim_products dp ON dp.product_id = foi.product_id
                     WHERE foi.product_id IS NOT NULL AND dp.product_id IS NULL) AS orphan_product_ref
            """,
            "SAMPLE_BAD_ORDERS (date=epoch)": """
                SELECT order_id, store_id, customer_id, order_date, gross_value, order_status
                FROM fact_orders
                WHERE order_date = '1970-01-01'::timestamp
                LIMIT 5
            """,
            "SAMPLE_ZERO_SUM_RAW": """
                SELECT order_id, user_id, date, sum, status_id, code
                FROM raw_orders WHERE sum = 0 LIMIT 5
            """,
            "RAW_CUSTOMERS_NAMES_SAMPLE": """
                SELECT user_id, email, firstname, lastname, group_id
                FROM raw_customers
                WHERE firstname IS NULL OR btrim(firstname) = ''
                LIMIT 10
            """,
        }

        for label, sql in queries.items():
            print(f"\n=== {label} ===")
            try:
                r = c.execute(text(sql))
                rows = r.fetchall()
                keys = list(r.keys())
                for row in rows:
                    for k, v in zip(keys, row):
                        print(f"  {k}: {v}")
                    if len(rows) > 1:
                        print("  ---")
            except Exception as ex:
                print(f"  ERROR: {ex}")


if __name__ == "__main__":
    run()
