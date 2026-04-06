"""Deep-dive data quality checks."""
from sqlalchemy import create_engine, text

DB_URL = "postgresql://postgres:2402@localhost:5432/bi_shoper"


def run():
    e = create_engine(DB_URL)
    with e.connect() as c:
        queries = {
            "RAW_ORDERS.STATUS JSON values (top 15)": """
                SELECT status::text, COUNT(*)
                FROM raw_orders
                GROUP BY status::text
                ORDER BY count DESC
                LIMIT 15
            """,
            "RAW confirm_date + is_paid": """
                SELECT COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE confirm_date IS NULL OR btrim(confirm_date) = '') AS confirm_null,
                    COUNT(*) FILTER (WHERE confirm_date = '0000-00-00 00:00:00') AS confirm_zero,
                    COUNT(*) FILTER (WHERE is_paid = true) AS is_paid_true,
                    COUNT(*) FILTER (WHERE is_paid = true AND (confirm_date IS NULL OR btrim(confirm_date) = '' OR confirm_date = '0000-00-00 00:00:00')) AS paid_no_confirm
                FROM raw_orders
            """,
            "RAW_CUSTOMERS name patterns": """
                SELECT
                    COUNT(*) FILTER (WHERE firstname IS NULL AND lastname IS NOT NULL AND btrim(lastname) != '') AS fn_null_ln_filled,
                    COUNT(*) FILTER (WHERE firstname IS NOT NULL AND btrim(firstname) != '' AND (lastname IS NULL OR btrim(lastname) = '')) AS fn_filled_ln_null,
                    COUNT(*) FILTER (WHERE (firstname IS NULL OR btrim(firstname) = '') AND (lastname IS NULL OR btrim(lastname) = '')) AS both_empty
                FROM raw_customers
            """,
            "ORPHAN product_ids (in items but NOT in dim_products)": """
                SELECT foi.product_id, COUNT(*) AS cnt
                FROM fact_order_items foi
                LEFT JOIN dim_products dp ON dp.product_id = foi.product_id
                WHERE foi.product_id IS NOT NULL AND dp.product_id IS NULL
                GROUP BY foi.product_id
                ORDER BY cnt DESC
                LIMIT 10
            """,
            "RAW_PRODUCTS.EAN top values": """
                SELECT ean, COUNT(*) FROM raw_products GROUP BY ean ORDER BY count DESC LIMIT 5
            """,
            "RAW_ORDERS status_id distribution": """
                SELECT status_id, COUNT(*) AS cnt
                FROM raw_orders
                GROUP BY status_id
                ORDER BY cnt DESC
            """,
            "FACT_ORDERS source_channel distribution": """
                SELECT source_channel, COUNT(*) AS cnt
                FROM fact_orders
                GROUP BY source_channel
                ORDER BY cnt DESC
            """,
            "RAW_ORDERS.user_id=NULL sample": """
                SELECT order_id, date, sum, status_id, email, code
                FROM raw_orders
                WHERE user_id IS NULL
                LIMIT 5
            """,
            "FACT_ORDER_ITEMS category_id=NULL top products": """
                SELECT foi.product_id, COUNT(*) AS cnt
                FROM fact_order_items foi
                WHERE foi.category_id IS NULL
                GROUP BY foi.product_id
                ORDER BY cnt DESC
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
                        val = str(v)[:200] if v is not None else "NULL"
                        print(f"  {k}: {val}")
                    if len(rows) > 1:
                        print("  ---")
                if not rows:
                    print("  (no rows)")
            except Exception as ex:
                print(f"  ERROR: {ex}")


if __name__ == "__main__":
    run()
