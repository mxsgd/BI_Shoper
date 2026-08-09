from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .common import FocusDateOutOfPeriodError, delta_pct, period_bounds


class OverviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(
        self,
        store_id: int,
        period: int,
        focus_date: date | None = None,
    ) -> dict:
        cur_start, cur_end, prev_start, prev_end = period_bounds(period)

        if focus_date is not None:
            if focus_date < cur_start or focus_date > cur_end:
                raise FocusDateOutOfPeriodError("focus_date outside selected period")
            return await self._overview_focus_day(store_id, period, focus_date)

        return await self._overview_period(
            store_id, period, cur_start, cur_end, prev_start, prev_end
        )

    async def _overview_focus_day(
        self, store_id: int, period: int, focus_date: date
    ) -> dict:
        prev_day = focus_date - timedelta(days=1)
        sql = text("""
            WITH cur AS (
                SELECT
                    COALESCE(SUM(gross_value), 0)   AS revenue,
                    COUNT(*)                         AS orders,
                    COUNT(DISTINCT customer_id)      AS customers,
                    COALESCE(AVG(gross_value), 0)    AS aov,
                    COALESCE(AVG(items_count), 0)    AS avg_items,
                    COUNT(*) FILTER (WHERE payment_status = 'paid') AS paid_orders
                FROM fact_orders
                WHERE store_id = :store_id
                    AND order_date::date = :focus_date
            ),
            prev AS (
                SELECT
                    COALESCE(SUM(gross_value), 0)   AS revenue,
                    COUNT(*)                         AS orders,
                    COUNT(DISTINCT customer_id)      AS customers,
                    COALESCE(AVG(gross_value), 0)    AS aov
                FROM fact_orders
                WHERE store_id = :store_id
                    AND order_date::date = :prev_day
            )
            SELECT
                cur.revenue, cur.orders, cur.customers, cur.aov,
                cur.avg_items, cur.paid_orders,
                prev.revenue  AS prev_revenue,
                prev.orders   AS prev_orders,
                prev.customers AS prev_customers,
                prev.aov      AS prev_aov
            FROM cur, prev
        """)
        row = (await self.db.execute(sql, {
            "store_id": store_id,
            "focus_date": focus_date,
            "prev_day": prev_day,
        })).one()
        return self._serialize_row(
            row,
            period_days=period,
            focus_date=focus_date,
            date_from=focus_date,
            date_to=focus_date,
        )

    async def _overview_period(
        self,
        store_id: int,
        period: int,
        cur_start: date,
        cur_end: date,
        prev_start: date,
        prev_end: date,
    ) -> dict:
        sql = text("""
            WITH cur AS (
                SELECT
                    COALESCE(SUM(gross_value), 0)   AS revenue,
                    COUNT(*)                         AS orders,
                    COUNT(DISTINCT customer_id)      AS customers,
                    COALESCE(AVG(gross_value), 0)    AS aov,
                    COALESCE(AVG(items_count), 0)    AS avg_items,
                    COUNT(*) FILTER (WHERE payment_status = 'paid') AS paid_orders
                FROM fact_orders
                WHERE store_id = :store_id
                    AND order_date::date BETWEEN :cur_start AND :cur_end
            ),
            prev AS (
                SELECT
                    COALESCE(SUM(gross_value), 0)   AS revenue,
                    COUNT(*)                         AS orders,
                    COUNT(DISTINCT customer_id)      AS customers,
                    COALESCE(AVG(gross_value), 0)    AS aov
                FROM fact_orders
                WHERE store_id = :store_id
                    AND order_date::date BETWEEN :prev_start AND :prev_end
            )
            SELECT
                cur.revenue, cur.orders, cur.customers, cur.aov,
                cur.avg_items, cur.paid_orders,
                prev.revenue  AS prev_revenue,
                prev.orders   AS prev_orders,
                prev.customers AS prev_customers,
                prev.aov      AS prev_aov
            FROM cur, prev
        """)
        row = (await self.db.execute(sql, {
            "store_id": store_id,
            "cur_start": cur_start,
            "cur_end": cur_end,
            "prev_start": prev_start,
            "prev_end": prev_end,
        })).one()
        return self._serialize_row(
            row,
            period_days=period,
            focus_date=None,
            date_from=cur_start,
            date_to=cur_end,
        )

    @staticmethod
    def _serialize_row(
        row,
        *,
        period_days: int,
        focus_date: date | None,
        date_from: date,
        date_to: date,
    ) -> dict:
        return {
            "period_days": period_days,
            "focus_date": str(focus_date) if focus_date else None,
            "date_from": str(date_from),
            "date_to": str(date_to),
            "revenue": round(float(row.revenue), 2),
            "revenue_delta_pct": delta_pct(row.revenue, row.prev_revenue),
            "orders": row.orders,
            "orders_delta_pct": delta_pct(row.orders, row.prev_orders),
            "aov": round(float(row.aov), 2),
            "aov_delta_pct": delta_pct(row.aov, row.prev_aov),
            "customers": row.customers,
            "customers_delta_pct": delta_pct(row.customers, row.prev_customers),
            "avg_items_per_order": round(float(row.avg_items), 1),
            "paid_pct": round(row.paid_orders / row.orders * 100, 1) if row.orders else 0,
        }
