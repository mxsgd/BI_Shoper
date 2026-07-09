from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TrendsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_trends(
        self,
        store_id: int,
        period: int,
    ) -> dict:
        since = date.today() - timedelta(days=period - 1)
        today = date.today()

        daily_rows = await self._fetch_daily_rows(store_id, since, today)
        monthly_rows = await self._fetch_monthly_rows(store_id)
        weekday_rows = await self._fetch_weekday_rows(store_id, since)

        return self._serialize(period, daily_rows, monthly_rows, weekday_rows)

    async def _fetch_daily_rows(self, store_id: int, since: date, today: date):
        daily_sql = text("""
            SELECT
                d.date                       AS dt,
                COALESCE(agg.revenue, 0)     AS revenue,
                COALESCE(agg.orders, 0)      AS orders,
                AVG(COALESCE(agg.revenue, 0)) OVER (
                    ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS ma7,
                AVG(COALESCE(agg.revenue, 0)) OVER (
                    ORDER BY d.date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
                ) AS ma30
            FROM generate_series(CAST(:since AS date), CAST(:today AS date), interval '1 day') AS d(date)
            LEFT JOIN (
                SELECT order_date::date AS odate,
                        SUM(gross_value) AS revenue,
                        COUNT(*)         AS orders
                FROM fact_orders
                WHERE store_id = :store_id AND order_date::date >= :since
                GROUP BY order_date::date
            ) agg ON agg.odate = d.date
            ORDER BY d.date
        """)
        return (await self.db.execute(daily_sql, {
            "store_id": store_id,
            "since": since,
            "today": today,
        })).all()

    async def _fetch_monthly_rows(self, store_id: int):
        monthly_sql = text("""
            WITH monthly AS (
                SELECT
                    date_trunc('month', order_date)::date AS month,
                    SUM(gross_value)  AS revenue,
                    COUNT(*)          AS orders
                FROM fact_orders
                WHERE store_id = :store_id
                GROUP BY month
                ORDER BY month
            )
            SELECT
                month,
                revenue,
                orders,
                ROUND(
                    (revenue - LAG(revenue) OVER (ORDER BY month))
                    / NULLIF(LAG(revenue) OVER (ORDER BY month), 0) * 100, 1
                ) AS mom_growth_pct,
                ROUND(
                    (revenue - LAG(revenue, 12) OVER (ORDER BY month))
                    / NULLIF(LAG(revenue, 12) OVER (ORDER BY month), 0) * 100, 1
                ) AS yoy_growth_pct
            FROM monthly
        """)
        return (await self.db.execute(monthly_sql, {"store_id": store_id})).all()

    async def _fetch_weekday_rows(self, store_id: int, since: date):
        weekday_sql = text("""
            SELECT
                EXTRACT(ISODOW FROM d)::int AS day_of_week,
                ROUND(AVG(daily_rev)::numeric, 2)    AS avg_revenue,
                ROUND(AVG(daily_ord)::numeric, 1)    AS avg_orders
            FROM (
                SELECT order_date::date AS d,
                        SUM(gross_value) AS daily_rev,
                        COUNT(*)         AS daily_ord
                FROM fact_orders
                WHERE store_id = :store_id AND order_date::date >= :since
                GROUP BY order_date::date
            ) sub
            GROUP BY EXTRACT(ISODOW FROM d)
            ORDER BY day_of_week
        """)
        return (await self.db.execute(weekday_sql, {
            "store_id": store_id,
            "since": since,
        })).all()

    @staticmethod
    def _serialize(period, daily_rows, monthly_rows, weekday_rows) -> dict:
        return {
            "period_days": period,
            "daily": [
                {
                    "date": str(r.dt),
                    "revenue": round(float(r.revenue), 2),
                    "orders": int(r.orders),
                    "ma7": round(float(r.ma7), 2) if r.ma7 else 0,
                    "ma30": round(float(r.ma30), 2) if r.ma30 else 0,
                }
                for r in daily_rows
            ],
            "monthly": [
                {
                    "month": str(r.month),
                    "revenue": round(float(r.revenue), 2),
                    "orders": r.orders,
                    "mom_growth_pct": float(r.mom_growth_pct) if r.mom_growth_pct is not None else None,
                    "yoy_growth_pct": float(r.yoy_growth_pct) if r.yoy_growth_pct is not None else None,
                }
                for r in monthly_rows
            ],
            "weekday_pattern": [
                {
                    "day_of_week": r.day_of_week,
                    "avg_revenue": float(r.avg_revenue),
                    "avg_orders": float(r.avg_orders),
                }
                for r in weekday_rows
            ],
        }
