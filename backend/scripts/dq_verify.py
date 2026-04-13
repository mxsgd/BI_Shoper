"""Verify fixes: order_status, payment_date, orphans."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from sqlalchemy import create_engine, text

DB_URL = "postgresql://postgres:2402@localhost:5432/bi_shoper"


def run():
    e = create_engine(DB_URL)
    with e.connect() as c:
        queries = {
            "FACT_ORDERS order_status": """
                SELECT order_status, COUNT(*) AS cnt
                FROM fact_orders
                GROUP BY order_status
                ORDER BY cnt DESC
            """,
            "FACT_ORDERS payment_date stats": """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE payment_date IS NOT NULL) AS has_payment_date,
                    COUNT(*) FILTER (WHERE payment_date IS NULL AND payment_status = 'paid') AS paid_no_date,
                    COUNT(*) FILTER (WHERE payment_status = 'paid') AS paid_total,
                    COUNT(*) FILTER (WHERE payment_status = 'unpaid') AS unpaid_total
                FROM fact_orders
            """,
            "RAW_STATUSES (new table)": """
                SELECT status_id, name, type FROM raw_statuses ORDER BY status_id
            """,
            "FACT_ORDERS status_empty check": """
                SELECT COUNT(*) FILTER (WHERE order_status IS NULL OR btrim(order_status) = '') AS still_empty
                FROM fact_orders
            """,
            "FACT_ORDER_ITEMS orphan check": """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE category_id IS NULL) AS category_null,
                    (SELECT COUNT(*) FROM fact_order_items foi
                     LEFT JOIN dim_products dp ON dp.product_id = foi.product_id
                     WHERE foi.product_id IS NOT NULL AND dp.product_id IS NULL) AS orphan_product_ref
                FROM fact_order_items
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
                if not rows:
                    print("  (no rows)")
            except Exception as ex:
                print(f"  ERROR: {ex}")


if __name__ == "__main__":
    run()
