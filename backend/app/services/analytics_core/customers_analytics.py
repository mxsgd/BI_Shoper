from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CustomersAnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_customers_analytics(
        self,
        store_id: int,
        period: int,
    ) -> dict:
        since = date.today() - timedelta(days=period - 1)
        today = date.today()

        seg_rows = await self._fetch_segmentation(store_id)
        top_rows = await self._fetch_top_customers(store_id)
        new_rows = await self._fetch_new_customers_monthly(store_id, since, today)
        repeat_row = await self._fetch_repeat_rate(store_id)

        return self._serialize(period, seg_rows, top_rows, new_rows, repeat_row)

    async def _fetch_segmentation(self, store_id: int):
        seg_sql = text("""
            SELECT
                customer_type,
                COUNT(*)                           AS count,
                COALESCE(SUM(total_revenue), 0)    AS revenue,
                COALESCE(AVG(total_orders), 0)     AS avg_orders,
                COALESCE(AVG(total_revenue), 0)    AS avg_revenue
            FROM dim_customers
            WHERE store_id = :store_id
            GROUP BY customer_type
        """)
        return (await self.db.execute(seg_sql, {"store_id": store_id})).all()

    async def _fetch_top_customers(self, store_id: int):
        top_sql = text("""
            SELECT
                dc.customer_id,
                dc.total_orders,
                dc.total_revenue,
                dc.first_order_date,
                dc.last_order_date,
                dc.customer_type
            FROM dim_customers dc
            WHERE dc.store_id = :store_id AND dc.total_revenue > 0
            ORDER BY dc.total_revenue DESC
            LIMIT 20
        """)
        return (await self.db.execute(top_sql, {"store_id": store_id})).all()

    async def _fetch_new_customers_monthly(self, store_id: int, since: date, today: date):
        new_sql = text("""
            SELECT
                d.month::date AS month,
                COALESCE(agg.new_customers, 0) AS new_customers
            FROM generate_series(
                date_trunc('month', CAST(:since AS date))::date,
                date_trunc('month', CAST(:today AS date))::date,
                interval '1 month'
            ) AS d(month)
            LEFT JOIN (
                SELECT
                    date_trunc('month', first_order_date)::date AS month,
                    COUNT(*) AS new_customers
                FROM dim_customers
                WHERE store_id = :store_id
                    AND first_order_date IS NOT NULL
                    AND first_order_date::date >= :since
                GROUP BY month
            ) agg ON agg.month = d.month::date
            ORDER BY d.month
        """)
        return (await self.db.execute(new_sql, {
            "store_id": store_id,
            "since": since,
            "today": today,
        })).all()

    async def _fetch_repeat_rate(self, store_id: int):
        repeat_sql = text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE total_orders > 1) AS repeat_buyers,
                COUNT(*) FILTER (WHERE total_orders = 1) AS one_time
            FROM dim_customers
            WHERE store_id = :store_id AND total_orders > 0
        """)
        return (await self.db.execute(repeat_sql, {"store_id": store_id})).one()

    @staticmethod
    def _serialize(period, seg_rows, top_rows, new_rows, repeat_row) -> dict:
        return {
            "period_days": period,
            "segmentation": [
                {
                    "type": r.customer_type,
                    "count": r.count,
                    "revenue": round(float(r.revenue), 2),
                    "avg_orders": round(float(r.avg_orders), 1),
                    "avg_revenue": round(float(r.avg_revenue), 2),
                }
                for r in seg_rows
            ],
            "top_customers": [
                {
                    "customer_id": r.customer_id,
                    "total_orders": r.total_orders,
                    "total_revenue": round(float(r.total_revenue), 2),
                    "first_order": str(r.first_order_date.date()) if r.first_order_date else None,
                    "last_order": str(r.last_order_date.date()) if r.last_order_date else None,
                    "type": r.customer_type,
                }
                for r in top_rows
            ],
            "new_customers_monthly": [
                {"month": str(r.month), "count": r.new_customers}
                for r in new_rows
            ],
            "retention": {
                "total_buyers": repeat_row.total,
                "repeat_buyers": repeat_row.repeat_buyers,
                "one_time_buyers": repeat_row.one_time,
                "repeat_rate_pct": round(
                    repeat_row.repeat_buyers / repeat_row.total * 100, 1
                ) if repeat_row.total else 0,
            },
        }
