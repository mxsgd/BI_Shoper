from datetime import date, timedelta

from typing_extensions import Literal
from common import date_bucket_series_sql

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ChannelsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_channels(
            self,
            store_id: int,
            period: int,
            group_by: Literal["day", "week", "month"] = "month") -> dict:

        since = date.today() - timedelta(days=period - 1)
        today = date.today()
        bucket_from = date_bucket_series_sql(group_by)

        ts_sql = text(f"""
            WITH buckets AS (SELECT bucket::date AS bucket FROM {bucket_from})
            SELECT
                bu.bucket,
                agg.source_channel AS channel,
                COALESCE(agg.orders, 0) AS orders,
                COALESCE(agg.revenue, 0) AS revenue
            FROM buckets bu
            LEFT JOIN (
                SELECT
                    date_trunc(:trunc, order_date)::date AS bucket,
                    source_channel,
                    COUNT(*) AS orders,
                    COALESCE(SUM(gross_value), 0) AS revenue
                FROM fact_orders
                WHERE store_id = :store_id AND order_date::date >= :since
                GROUP BY date_trunc(:trunc, order_date)::date, source_channel
            ) agg ON agg.bucket = bu.bucket
            ORDER BY bu.bucket, agg.source_channel NULLS LAST
        """)
        ts_rows = (await self.db.execute(ts_sql, {
            "store_id": store_id,
            "since": since,
            "today": today,
            "trunc": group_by,
        })).all()

        time_map: dict[str, dict] = {}
        for r in ts_rows:
            key = str(r.bucket)
            if key not in time_map:
                time_map[key] = {"date": key}
            if r.source_channel is not None:
                ch = r.source_channel or "other"
                time_map[key][ch] = round(float(r.revenue), 2)

        summary_sql = text("""
            SELECT
                source_channel,
                COUNT(*)                          AS total_orders,
                COALESCE(SUM(gross_value), 0)     AS total_revenue,
                COALESCE(AVG(gross_value), 0)     AS aov
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date >= :since
            GROUP BY source_channel
            ORDER BY total_revenue DESC
        """)

        summary_rows = (await self.db.execute(summary_sql, {
            "store_id": store_id, "since": since,
        })).all()

        grand_total = sum(float(r.total_revenue) for r in summary_rows) or 1

        channel_names = [r.source_channel or "other" for r in summary_rows]
        time_series = []
        for key in sorted(time_map):
            row = dict(time_map[key])
            for ch in channel_names:
                row.setdefault(ch, 0)
            time_series.append(row)
    
        return {
            "period_days": period,
            "time_series": time_series,
            "channels": channel_names,
            "summary": [
                {
                    "channel": r.source_channel or "other",
                    "total_orders": r.total_orders,
                    "total_revenue": round(float(r.total_revenue), 2),
                    "aov": round(float(r.aov), 2),
                    "pct_of_total": round(float(r.total_revenue) / grand_total * 100, 1),
                }
                for r in summary_rows
            ],
        }
        