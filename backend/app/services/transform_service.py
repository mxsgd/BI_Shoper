"""
Transform service: RAW staging tables --> CORE star schema.

Runs after sync to populate fact_orders, fact_order_items,
dim_customers, dim_products, dim_categories.

All transforms use INSERT … ON CONFLICT DO UPDATE so they are
idempotent and safe to re-run.
"""

import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Shoper / legacy MySQL sometimes stores "0000-00-00 00:00:00"; PostgreSQL rejects ::timestamp.
def _sql_safe_timestamp(col_sql: str) -> str:
    # Avoid LIKE '0000%' inside f-strings (%% is not reduced to % in f-strings).
    return (
        f"CASE WHEN {col_sql} IS NULL OR btrim({col_sql}::text) = '' THEN NULL "
        f"WHEN substring(btrim({col_sql}::text) FROM 1 FOR 4) = '0000' THEN NULL "
        f"ELSE {col_sql}::timestamp END"
    )


ORIGIN_MAP = {
    0: "shop",
    1: "facebook",
    2: "mobile",
    3: "allegro",
    4: "webapi",
    5: "panel",
    6: "admin",
    8: "google",
}


class TransformService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_all(self) -> dict:
        """Run every transform phase and return counts."""
        cats = await self.transform_dim_categories()
        prods = await self.transform_dim_products()
        custs = await self.transform_dim_customers()
        orders = await self.transform_fact_orders()
        items = await self.transform_fact_order_items()
        date_rows = await self.ensure_dim_date()
        result = {
            "dim_categories": cats,
            "dim_products": prods,
            "dim_customers": custs,
            "fact_orders": orders,
            "fact_order_items": items,
            "dim_date": date_rows,
        }
        logger.info("Transform complete: %s", result)
        return result

    # ------------------------------------------------------------------
    # dim_categories
    # ------------------------------------------------------------------
    async def transform_dim_categories(self) -> int:
        sql = text("""
            INSERT INTO dim_categories (category_id, category_name, parent_id)
            SELECT
                rc.category_id,
                COALESCE(
                    rc.translations -> 'pl_PL' ->> 'name',
                    rc.translations -> 'en_GB' ->> 'name',
                    'Category #' || rc.category_id
                ),
                (rc.translations ->> '_parent_id')::int
            FROM raw_categories rc
            ON CONFLICT (category_id) DO UPDATE SET
                category_name = EXCLUDED.category_name,
                parent_id     = EXCLUDED.parent_id
        """)
        result = await self.db.execute(sql)
        await self.db.commit()
        return result.rowcount

    # ------------------------------------------------------------------
    # dim_products
    # ------------------------------------------------------------------
    async def transform_dim_products(self) -> int:
        sql = text("""
            INSERT INTO dim_products (
                product_id, store_id, product_name, category_id,
                brand, cost_price, retail_price, is_active
            )
            SELECT
                rp.product_id,
                rp.store_id,
                COALESCE(
                    rp.translations -> 'pl_PL' ->> 'name',
                    rp.translations -> 'en_GB' ->> 'name',
                    'Product #' || rp.product_id
                ),
                rp.category_id,
                rprod.name,
                COALESCE(
                    base_stock.price_buying,
                    (rp.stock ->> 'price_wholesale')::numeric
                ),
                COALESCE(
                    base_stock.price,
                    (rp.stock ->> 'price')::numeric
                ),
                COALESCE(
                    (rp.translations -> 'pl_PL' ->> 'active')::int = 1,
                    true
                )
            FROM raw_products rp
            LEFT JOIN raw_producers rprod
                ON rprod.store_id = rp.store_id AND rprod.producer_id = rp.producer_id
            LEFT JOIN raw_product_stocks base_stock
                ON base_stock.store_id = rp.store_id
                AND base_stock.product_id = rp.product_id
                AND COALESCE(base_stock.extended, false) = false
            ON CONFLICT (product_id) DO UPDATE SET
                product_name = EXCLUDED.product_name,
                category_id  = EXCLUDED.category_id,
                brand        = EXCLUDED.brand,
                cost_price   = EXCLUDED.cost_price,
                retail_price = EXCLUDED.retail_price,
                is_active    = EXCLUDED.is_active,
                updated_at   = now()
        """)
        result = await self.db.execute(sql)
        await self.db.commit()
        return result.rowcount

    # ------------------------------------------------------------------
    # dim_customers
    # ------------------------------------------------------------------
    async def transform_dim_customers(self) -> int:
        sql = text(f"""
            INSERT INTO dim_customers (
                customer_id, store_id,
                first_order_date, last_order_date,
                total_orders, total_revenue,
                customer_type
            )
            SELECT
                rc.user_id,
                rc.store_id,
                agg.first_order,
                agg.last_order,
                COALESCE(agg.order_count, 0),
                COALESCE(agg.revenue, 0),
                CASE WHEN COALESCE(agg.order_count, 0) <= 1 THEN 'new' ELSE 'returning' END
            FROM raw_customers rc
            LEFT JOIN (
                SELECT
                    ro.store_id,
                    ro.user_id,
                    MIN({_sql_safe_timestamp("ro.date")}) AS first_order,
                    MAX({_sql_safe_timestamp("ro.date")}) AS last_order,
                    COUNT(*)                AS order_count,
                    SUM(ro.sum)             AS revenue
                FROM raw_orders ro
                WHERE ro.user_id IS NOT NULL
                GROUP BY ro.store_id, ro.user_id
            ) agg ON agg.store_id = rc.store_id AND agg.user_id = rc.user_id
            ON CONFLICT (customer_id) DO UPDATE SET
                first_order_date = EXCLUDED.first_order_date,
                last_order_date  = EXCLUDED.last_order_date,
                total_orders     = EXCLUDED.total_orders,
                total_revenue    = EXCLUDED.total_revenue,
                customer_type    = EXCLUDED.customer_type,
                updated_at       = now()
        """)
        result = await self.db.execute(sql)
        await self.db.commit()
        count = result.rowcount

        rfm_sql = text("""
            WITH rfm AS (
                SELECT
                    customer_id,
                    NTILE(5) OVER (ORDER BY last_order_date ASC)  AS r,
                    NTILE(5) OVER (ORDER BY total_orders)         AS f,
                    NTILE(5) OVER (ORDER BY total_revenue)        AS m
                FROM dim_customers
                WHERE total_orders > 0
            )
            UPDATE dim_customers dc
            SET rfm_score = rfm.r::text || rfm.f::text || rfm.m::text,
                updated_at = now()
            FROM rfm
            WHERE dc.customer_id = rfm.customer_id
        """)
        await self.db.execute(rfm_sql)
        await self.db.commit()
        return count

    # ------------------------------------------------------------------
    # fact_orders
    # ------------------------------------------------------------------
    async def transform_fact_orders(self) -> int:
        origin_cases = "\n".join(
            f"WHEN {k} THEN '{v}'" for k, v in ORIGIN_MAP.items()
        )
        ts_order = _sql_safe_timestamp("ro.date")
        ts_status = _sql_safe_timestamp("ro.status_date")
        sql = text(f"""
            INSERT INTO fact_orders (
                order_id, store_id, customer_id,
                order_date, payment_date,
                order_status, payment_status, shipment_status,
                gross_value, net_value, discount_value,
                shipping_value, tax_value, margin_value,
                items_count,
                source_channel, campaign
            )
            SELECT
                ro.order_id,
                ro.store_id,
                ro.user_id,
                COALESCE({ts_order}, '1970-01-01 00:00:00+00'::timestamptz),
                CASE WHEN ro.is_paid THEN {ts_status} ELSE NULL END,
                COALESCE(rs.name, 'Status #' || ro.status_id),
                CASE WHEN ro.is_paid THEN 'paid' ELSE 'unpaid' END,
                NULL,
                ro.sum,
                COALESCE(items_net.total_net, ro.sum),
                GREATEST(
                    ro.discount_client + ro.discount_group
                    + ro.discount_levels + ro.discount_code, 0
                ),
                ro.shipping_cost,
                ro.sum - COALESCE(items_net.total_net, ro.sum),
                COALESCE(items_cost.total_cost, 0),
                COALESCE(ro.total_products, 0),
                CASE ro.origin {origin_cases} ELSE 'other' END,
                ro.promo_code
            FROM raw_orders ro
            LEFT JOIN raw_statuses rs
                ON rs.store_id = ro.store_id AND rs.status_id = ro.status_id
            LEFT JOIN (
                SELECT roi.store_id, roi.order_id,
                       SUM(roi.price * roi.quantity
                           / (1 + COALESCE(NULLIF(roi.tax_value, 0), 23) / 100.0))
                       AS total_net
                FROM raw_order_items roi
                GROUP BY roi.store_id, roi.order_id
            ) items_net
                ON items_net.store_id = ro.store_id AND items_net.order_id = ro.order_id
            LEFT JOIN (
                SELECT roi2.store_id, roi2.order_id,
                       SUM(COALESCE(ps.price_buying, 0) * roi2.quantity) AS total_cost
                FROM raw_order_items roi2
                LEFT JOIN raw_product_stocks ps
                    ON ps.store_id = roi2.store_id
                    AND ps.product_id = roi2.product_id
                    AND COALESCE(ps.extended, false) = false
                GROUP BY roi2.store_id, roi2.order_id
            ) items_cost
                ON items_cost.store_id = ro.store_id AND items_cost.order_id = ro.order_id
            ON CONFLICT (order_id) DO UPDATE SET
                customer_id    = EXCLUDED.customer_id,
                order_date     = EXCLUDED.order_date,
                payment_date   = EXCLUDED.payment_date,
                order_status   = EXCLUDED.order_status,
                payment_status = EXCLUDED.payment_status,
                gross_value    = EXCLUDED.gross_value,
                net_value      = EXCLUDED.net_value,
                discount_value = EXCLUDED.discount_value,
                shipping_value = EXCLUDED.shipping_value,
                tax_value      = EXCLUDED.tax_value,
                margin_value   = EXCLUDED.margin_value,
                items_count    = EXCLUDED.items_count,
                source_channel = EXCLUDED.source_channel,
                campaign       = EXCLUDED.campaign,
                updated_at     = now()
        """)
        result = await self.db.execute(sql)
        await self.db.commit()
        return result.rowcount

    # ------------------------------------------------------------------
    # fact_order_items
    # ------------------------------------------------------------------
    async def transform_fact_order_items(self) -> int:
        ts_order = _sql_safe_timestamp("ro.date")
        sql = text(f"""
            INSERT INTO fact_order_items (
                order_item_id, order_id, product_id, category_id,
                quantity, unit_price_gross, unit_price_net,
                discount_value, total_gross, total_net,
                order_date
            )
            SELECT
                roi.order_item_id,
                roi.order_id,
                roi.product_id,
                rp.category_id,
                roi.quantity::int,
                roi.price,
                roi.price / (1 + COALESCE(rt.value, NULLIF(roi.tax_value, 0), 23) / 100.0),
                roi.price * roi.discount_perc / 100.0,
                roi.price * roi.quantity,
                roi.price * roi.quantity / (1 + COALESCE(rt.value, NULLIF(roi.tax_value, 0), 23) / 100.0),
                COALESCE({ts_order}, '1970-01-01 00:00:00+00'::timestamptz)
            FROM raw_order_items roi
            JOIN raw_orders ro
                ON ro.store_id = roi.store_id AND ro.order_id = roi.order_id
            LEFT JOIN raw_products rp
                ON rp.store_id = roi.store_id AND rp.product_id = roi.product_id
            LEFT JOIN raw_taxes rt
                ON rt.store_id = rp.store_id AND rt.tax_id = rp.tax_id
            ON CONFLICT (order_item_id) DO UPDATE SET
                product_id       = EXCLUDED.product_id,
                category_id      = EXCLUDED.category_id,
                quantity         = EXCLUDED.quantity,
                unit_price_gross = EXCLUDED.unit_price_gross,
                unit_price_net   = EXCLUDED.unit_price_net,
                discount_value   = EXCLUDED.discount_value,
                total_gross      = EXCLUDED.total_gross,
                total_net        = EXCLUDED.total_net,
                order_date       = EXCLUDED.order_date
        """)
        result = await self.db.execute(sql)
        await self.db.commit()
        return result.rowcount

    # ------------------------------------------------------------------
    # dim_date  (ensure range covers all order dates + current year)
    # ------------------------------------------------------------------
    async def ensure_dim_date(self, start_year: int = 2020) -> int:
        end_year = date.today().year + 1
        result = await self.db.execute(text("SELECT COUNT(*) FROM dim_date"))
        existing = result.scalar() or 0
        if existing > 0:
            return 0

        rows = []
        current = date(start_year, 1, 1)
        end = date(end_year, 12, 31)
        while current <= end:
            iso_year, iso_week, _ = current.isocalendar()
            quarter = (current.month - 1) // 3 + 1
            rows.append({
                "date_id": current,
                "day": current.day,
                "month": current.month,
                "year": current.year,
                "week": iso_week,
                "quarter": quarter,
                "is_weekend": current.weekday() >= 5,
            })
            current += timedelta(days=1)

        if rows:
            placeholders = ", ".join(
                f"(:d{i}, :day{i}, :mo{i}, :yr{i}, :wk{i}, :qt{i}, :we{i})"
                for i in range(len(rows))
            )
            params = {}
            for i, r in enumerate(rows):
                params[f"d{i}"] = r["date_id"]
                params[f"day{i}"] = r["day"]
                params[f"mo{i}"] = r["month"]
                params[f"yr{i}"] = r["year"]
                params[f"wk{i}"] = r["week"]
                params[f"qt{i}"] = r["quarter"]
                params[f"we{i}"] = r["is_weekend"]

            batch_size = 500
            count = 0
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                values_parts = []
                batch_params = {}
                for i, r in enumerate(batch):
                    idx = start + i
                    values_parts.append(
                        f"(:d{idx}, :day{idx}, :mo{idx}, :yr{idx}, :wk{idx}, :qt{idx}, :we{idx})"
                    )
                    batch_params[f"d{idx}"] = r["date_id"]
                    batch_params[f"day{idx}"] = r["day"]
                    batch_params[f"mo{idx}"] = r["month"]
                    batch_params[f"yr{idx}"] = r["year"]
                    batch_params[f"wk{idx}"] = r["week"]
                    batch_params[f"qt{idx}"] = r["quarter"]
                    batch_params[f"we{idx}"] = r["is_weekend"]
                sql = text(
                    "INSERT INTO dim_date (date_id, day, month, year, week, quarter, is_weekend) "
                    f"VALUES {', '.join(values_parts)} ON CONFLICT DO NOTHING"
                )
                await self.db.execute(sql, batch_params)
                count += len(batch)
            await self.db.commit()
            logger.info("Seeded %d rows into dim_date (%d-%d)", count, start_year, end_year)
            return count
        return 0
