from datetime import date, timedelta, datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from common import _safe_table_exists_sql

class TrackerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def tracker_events_summary(
            self,
            store_id: int,
            period: int,) -> dict:

            # Zakładamy, że timestamp to Unix epoch w sekundach.
            now = datetime.utcnow()
            since_dt = now - timedelta(days=period)
            since_epoch = int(since_dt.timestamp())
        
            exists_sql = text(_safe_table_exists_sql("tracker_events_local"))
            if not (await db.execute(exists_sql)).scalar():
                return {
                    "period_days": period,
                    "total_events": 0,
                    "distinct_users": 0,
                    "since_iso": since_dt.isoformat() + "Z",
                    "by_event": [],
                    "top_urls": [],
                }
        
            agg_sql = text("""
                SELECT
                    COUNT(*)                        AS total_events,
                    COUNT(DISTINCT user_id)         AS distinct_users,
                    COALESCE(MAX(timestamp), 0)     AS last_ts
                FROM tracker_events_local
                WHERE timestamp >= :since_epoch
            """)
            agg_row = (await db.execute(agg_sql, {"since_epoch": since_epoch})).one()
        
            total_events = int(agg_row.total_events or 0)
            distinct_users = int(agg_row.distinct_users or 0)
        
            by_event_sql = text("""
                SELECT event_name, COUNT(*) AS cnt
                FROM tracker_events_local
                WHERE timestamp >= :since_epoch
                GROUP BY event_name
                ORDER BY cnt DESC
                LIMIT 20
            """)
            by_event_rows = (await db.execute(by_event_sql, {"since_epoch": since_epoch})).all()
        
            top_urls_sql = text("""
                SELECT url, COUNT(*) AS cnt
                FROM tracker_events_local
                WHERE timestamp >= :since_epoch
                GROUP BY url
                ORDER BY cnt DESC
                LIMIT 20
            """)
            top_url_rows = (await db.execute(top_urls_sql, {"since_epoch": since_epoch})).all()
        
            return {
                "period_days": period,
                "total_events": total_events,
                "distinct_users": distinct_users,
                "since_iso": since_dt.isoformat() + "Z",
                "by_event": [
                    {"event_name": r.event_name, "count": int(r.cnt)}
                    for r in by_event_rows
                ],
                "top_urls": [
                    {"url": r.url, "count": int(r.cnt)}
                    for r in top_url_rows
                ],
            }