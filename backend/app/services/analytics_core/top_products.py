from datetime import date, timedelta
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TopProductsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_top_products(
        self,
        store_id: int,
        period: int,
        limit: int = 20,
        sort_by: Literal["revenue", "quantity"] = "revenue",
    ) -> dict:
        since = date.today() - timedelta(days=period - 1)
        rows = await self._fetch_top_products(store_id, since, limit, sort_by)
        return self._serialize(period, sort_by, rows)

    async def _fetch_top_products(
        self,
        store_id: int,
        since: date,
        limit: int,
        sort_by: Literal["revenue", "quantity"],
    ):
        order_col = "revenue" if sort_by == "revenue" else "total_qty"
        sql = text(f"""
            WITH ranked AS (
                SELECT
                    foi.product_id,
                    dp.product_name,
                    dc.category_name,
                    SUM(foi.quantity)    AS total_qty,
                    SUM(foi.total_gross) AS revenue,
                    COUNT(DISTINCT foi.order_id) AS order_count
                FROM fact_order_items foi
                JOIN fact_orders fo
                    ON fo.order_id = foi.order_id
                LEFT JOIN dim_products dp
                    ON dp.product_id = foi.product_id
                LEFT JOIN dim_categories dc
                    ON dc.category_id = foi.category_id
                WHERE fo.store_id = :store_id
                    AND fo.order_date::date >= :since
                GROUP BY foi.product_id, dp.product_name, dc.category_name
            ),
            totals AS (
                SELECT SUM(revenue) AS grand_total FROM ranked
            )
            SELECT
                r.product_id,
                r.product_name,
                r.category_name,
                r.total_qty,
                r.revenue,
                r.order_count,
                ROUND(r.revenue / NULLIF(t.grand_total, 0) * 100, 2) AS revenue_pct,
                SUM(r.revenue) OVER (ORDER BY r.{order_col} DESC)
                    / NULLIF(t.grand_total, 0) * 100 AS cumulative_pct
            FROM ranked r, totals t
            ORDER BY r.{order_col} DESC
            LIMIT :lim
        """)
        return (await self.db.execute(sql, {
            "store_id": store_id,
            "since": since,
            "lim": limit,
        })).all()

    @staticmethod
    def _serialize(period: int, sort_by: str, rows) -> dict:
        return {
            "period_days": period,
            "sort_by": sort_by,
            "products": [
                {
                    "product_id": r.product_id,
                    "name": r.product_name or f"Product #{r.product_id}",
                    "category": r.category_name,
                    "quantity": int(r.total_qty),
                    "revenue": round(float(r.revenue), 2),
                    "orders": r.order_count,
                    "revenue_pct": float(r.revenue_pct or 0),
                    "cumulative_pct": round(float(r.cumulative_pct or 0), 2),
                }
                for r in rows
            ],
        }
