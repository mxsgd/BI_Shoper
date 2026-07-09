from datetime import date, timedelta
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .common import FocusDateOutOfPeriodError, date_bucket_series_sql


class RevenueService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_revenue(
        self,
        store_id: int,
        period: int,
        group_by: Literal["day", "week", "month"] = "day",
        focus_date: date | None = None,
    ) -> dict:
        cur_start = date.today() - timedelta(days=period - 1)
        today = date.today()

        if focus_date is not None and (focus_date < cur_start or focus_date > today):
            raise FocusDateOutOfPeriodError("focus_date outside selected period")

        ts_rows = await self._fetch_time_series(
            store_id, cur_start, today, group_by
        )

        if focus_date is not None:
            status_rows, channel_rows, category_rows = await self._fetch_breakdowns_for_day(
                store_id, focus_date
            )
        else:
            status_rows, channel_rows, category_rows = await self._fetch_breakdowns_for_period(
                store_id, cur_start
            )

        return self._serialize(
            period=period,
            group_by=group_by,
            focus_date=focus_date,
            ts_rows=ts_rows,
            status_rows=status_rows,
            channel_rows=channel_rows,
            category_rows=category_rows,
        )

    async def _fetch_time_series(
        self,
        store_id: int,
        since: date,
        today: date,
        group_by: Literal["day", "week", "month"],
    ):
        trunc = group_by
        bucket_from = date_bucket_series_sql(group_by)
        ts_sql = text(f"""
            SELECT
                b.bucket::date AS bucket,
                COALESCE(agg.orders, 0)              AS orders,
                COALESCE(agg.revenue, 0)             AS revenue,
                COALESCE(agg.discounts, 0)           AS discounts,
                COALESCE(agg.shipping, 0)            AS shipping
            FROM {bucket_from}
            LEFT JOIN (
                SELECT
                    date_trunc(:trunc, order_date)::date AS bucket,
                    COUNT(*)                              AS orders,
                    COALESCE(SUM(gross_value), 0)         AS revenue,
                    COALESCE(SUM(discount_value), 0)      AS discounts,
                    COALESCE(SUM(shipping_value), 0)      AS shipping
                FROM fact_orders
                WHERE store_id = :store_id
                    AND order_date::date >= :since
                GROUP BY bucket
            ) agg ON agg.bucket = b.bucket::date
            ORDER BY b.bucket
        """)
        return (await self.db.execute(ts_sql, {
            "store_id": store_id,
            "since": since,
            "today": today,
            "trunc": trunc,
        })).all()

    async def _fetch_breakdowns_for_day(self, store_id: int, focus_date: date):
        status_sql = text("""
            SELECT order_status, COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date = :focus_date
            GROUP BY order_status
            ORDER BY revenue DESC
        """)
        status_rows = (await self.db.execute(status_sql, {
            "store_id": store_id,
            "focus_date": focus_date,
        })).all()

        channel_sql = text("""
            SELECT source_channel, COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date = :focus_date
            GROUP BY source_channel
            ORDER BY revenue DESC
        """)
        channel_rows = (await self.db.execute(channel_sql, {
            "store_id": store_id,
            "focus_date": focus_date,
        })).all()

        category_sql = text("""
            SELECT
                COALESCE(dc.category_name, 'Bez kategorii') AS category,
                COUNT(DISTINCT foi.order_id) AS orders,
                COALESCE(SUM(foi.total_gross), 0) AS revenue,
                COALESCE(SUM(foi.quantity), 0) AS quantity
            FROM fact_order_items foi
            JOIN fact_orders fo ON fo.order_id = foi.order_id
            LEFT JOIN dim_categories dc ON dc.category_id = foi.category_id
            WHERE fo.store_id = :store_id AND fo.order_date::date = :focus_date
            GROUP BY COALESCE(dc.category_name, 'Bez kategorii')
            ORDER BY revenue DESC
        """)
        category_rows = (await self.db.execute(category_sql, {
            "store_id": store_id,
            "focus_date": focus_date,
        })).all()

        return status_rows, channel_rows, category_rows

    async def _fetch_breakdowns_for_period(self, store_id: int, since: date):
        status_sql = text("""
            SELECT order_status, COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date >= :since
            GROUP BY order_status
            ORDER BY revenue DESC
        """)
        status_rows = (await self.db.execute(status_sql, {
            "store_id": store_id,
            "since": since,
        })).all()

        channel_sql = text("""
            SELECT source_channel, COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date >= :since
            GROUP BY source_channel
            ORDER BY revenue DESC
        """)
        channel_rows = (await self.db.execute(channel_sql, {
            "store_id": store_id,
            "since": since,
        })).all()

        category_sql = text("""
            SELECT
                COALESCE(dc.category_name, 'Bez kategorii') AS category,
                COUNT(DISTINCT foi.order_id) AS orders,
                COALESCE(SUM(foi.total_gross), 0) AS revenue,
                COALESCE(SUM(foi.quantity), 0) AS quantity
            FROM fact_order_items foi
            JOIN fact_orders fo ON fo.order_id = foi.order_id
            LEFT JOIN dim_categories dc ON dc.category_id = foi.category_id
            WHERE fo.store_id = :store_id AND fo.order_date::date >= :since
            GROUP BY COALESCE(dc.category_name, 'Bez kategorii')
            ORDER BY revenue DESC
        """)
        category_rows = (await self.db.execute(category_sql, {
            "store_id": store_id,
            "since": since,
        })).all()

        return status_rows, channel_rows, category_rows

    @staticmethod
    def _serialize(
        *,
        period: int,
        group_by: str,
        focus_date: date | None,
        ts_rows,
        status_rows,
        channel_rows,
        category_rows,
    ) -> dict:
        return {
            "period_days": period,
            "group_by": group_by,
            "focus_date": str(focus_date) if focus_date else None,
            "time_series": [
                {
                    "date": str(r.bucket),
                    "orders": r.orders,
                    "revenue": round(float(r.revenue), 2),
                    "discounts": round(float(r.discounts), 2),
                    "shipping": round(float(r.shipping), 2),
                }
                for r in ts_rows
            ],
            "by_status": [
                {
                    "status": r.order_status,
                    "orders": r.orders,
                    "revenue": round(float(r.revenue), 2),
                }
                for r in status_rows
            ],
            "by_channel": [
                {
                    "channel": r.source_channel,
                    "orders": r.orders,
                    "revenue": round(float(r.revenue), 2),
                }
                for r in channel_rows
            ],
            "by_category": [
                {
                    "category": r.category,
                    "orders": r.orders,
                    "revenue": round(float(r.revenue), 2),
                    "quantity": int(r.quantity),
                }
                for r in category_rows
            ],
        }
