from datetime import date, timedelta

from typing_extensions import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

class TrafficService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_traffic(
            self,
            store_id: int,
            period: int,
            focus_date: Optional[date]) -> dict:

        since = date.today() - timedelta(days=period - 1)
        today = date.today()
        if focus_date is not None and (focus_date < since or focus_date > today):
            raise HTTPException(status_code=400, detail="focus_date outside selected period")

        has_ga4 = (await self.db.execute(text(
            "SELECT EXISTS (SELECT 1 FROM raw_ga4_traffic WHERE date >= :since)"
        ), {"since": since})).scalar()

        data_through = (await self.db.execute(text(
            "SELECT MAX(date) FROM raw_ga4_traffic"
        ))).scalar()

        if not has_ga4:
            return {
                "has_data": False,
                "data_through": str(data_through) if data_through else None,
                "overview": None, "conversion": None, "time_series": [],
                "sources": [], "top_pages": [], "geo": [], "devices": [],
                "funnel": None,
                "focus_date": None,
            }

        if focus_date is not None:
            overview_sql = text("""
                SELECT
                    COALESCE(SUM(session), 0)       AS sessions,
                    COALESCE(SUM(total_users), 0)   AS users,
                    COALESCE(SUM(new_users), 0)     AS new_users,
                    ROUND(AVG(bounce_rate)::numeric, 4) AS bounce_rate,
                    ROUND(AVG(avg_session_duration)::numeric, 1) AS avg_duration
                FROM raw_ga4_traffic
                WHERE date = :focus_date
            """)
            ov = (await self.db.execute(overview_sql, {"focus_date": focus_date})).one()
            orders_sql = text("""
                SELECT COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
                FROM fact_orders
                WHERE store_id = :store_id AND order_date::date = :focus_date
            """)
            ord_row = (await self.db.execute(orders_sql, {"store_id": store_id, "focus_date": focus_date})).one()
        else:
            overview_sql = text("""
                SELECT
                    COALESCE(SUM(sessions), 0)         AS sessions,
                    COALESCE(SUM(total_users), 0)      AS users,
                    COALESCE(SUM(new_users), 0)        AS new_users,
                    ROUND(AVG(bounce_rate)::numeric, 4) AS bounce_rate,
                    ROUND(AVG(avg_session_duration)::numeric, 1) AS avg_duration
                FROM raw_ga4_traffic
                WHERE date >= :since
            """)
            ov = (await self.db.execute(overview_sql, {"since": since})).one()
            orders_sql = text("""
                SELECT COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
                FROM fact_orders
                WHERE store_id = :store_id AND order_date::date >= :since
            """)
            ord_row = (await self.db.execute(orders_sql, {"store_id": store_id, "since": since})).one()

        ts_sql = text("""
            SELECT
                d.date::date AS date,
                COALESCE(t.sessions, 0) AS sessions,
                COALESCE(t.total_users, 0) AS users,
                COALESCE(o.orders, 0) AS orders,
                COALESCE(o.revenue, 0) AS revenue
            FROM generate_series(CAST(:since AS date), CAST(:today AS date), interval '1 day') AS d(date)
            LEFT JOIN raw_ga4_traffic t ON t.date = d.date::date
            LEFT JOIN (
                SELECT order_date::date AS odate, COUNT(*) AS orders, SUM(gross_value) AS revenue
                FROM fact_orders WHERE store_id = :store_id AND order_date::date >= :since
                GROUP BY order_date::date
            ) o ON o.odate = d.date::date
            ORDER BY d.date
        """)
        ts_rows = (await self.db.execute(ts_sql, {
            "store_id": store_id, "since": since, "today": today,
        })).all()

        if focus_date is not None:
            sources_sql = text("""
                SELECT source, medium,
                    SUM(sessions) AS sessions, SUM(users) AS users,
                    SUM(new_users) AS new_users, SUM(engaged_sessions) AS engaged,
                    SUM(conversions) AS conversions
                FROM raw_ga4_sources WHERE date = :focus_date
                GROUP BY source, medium
                ORDER BY sessions DESC
                LIMIT 30
            """)
            src_rows = (await self.db.execute(sources_sql, {"focus_date": focus_date})).all()
            pages_sql = text("""
                SELECT page_path,
                    SUM(page_views) AS views,
                    ROUND(AVG(avg_time_on_page)::numeric, 1) AS avg_time,
                    SUM(entrances) AS entrances
                FROM raw_ga4_pages WHERE date = :focus_date
                GROUP BY page_path
                ORDER BY views DESC
                LIMIT 20
            """)
            page_rows = (await self.db.execute(pages_sql, {"focus_date": focus_date})).all()
            geo_sql = text("""
                SELECT country, city,
                    SUM(sessions) AS sessions, SUM(users) AS users
                FROM raw_ga4_geo WHERE date = :focus_date
                GROUP BY country, city
                ORDER BY sessions DESC
                LIMIT 30
            """)
            geo_rows = (await self.db.execute(geo_sql, {"focus_date": focus_date})).all()
            devices_sql = text("""
                SELECT device_category,
                    SUM(sessions) AS sessions, SUM(users) AS users
                FROM raw_ga4_devices WHERE date = :focus_date
                GROUP BY device_category
                ORDER BY sessions DESC
            """)
            dev_rows = (await self.db.execute(devices_sql, {"focus_date": focus_date})).all()
        else:
            sources_sql = text("""
                SELECT source, medium,
                    SUM(sessions) AS sessions, SUM(users) AS users,
                    SUM(new_users) AS new_users, SUM(engaged_sessions) AS engaged,
                    SUM(conversions) AS conversions
                FROM raw_ga4_sources WHERE date >= :since
                GROUP BY source, medium
                ORDER BY sessions DESC
                LIMIT 30
            """)
            src_rows = (await self.db.execute(sources_sql, {"since": since})).all()
            pages_sql = text("""
                SELECT page_path,
                    SUM(page_views) AS views,
                    ROUND(AVG(avg_time_on_page)::numeric, 1) AS avg_time,
                    SUM(entrances) AS entrances
                FROM raw_ga4_pages WHERE date >= :since
                GROUP BY page_path
                ORDER BY views DESC
                LIMIT 20
            """)
            page_rows = (await self.db.execute(pages_sql, {"since": since})).all()
            geo_sql = text("""
                SELECT country, city,
                    SUM(sessions) AS sessions, SUM(users) AS users
                FROM raw_ga4_geo WHERE date >= :since
                GROUP BY country, city
                ORDER BY sessions DESC
                LIMIT 30
            """)
            geo_rows = (await self.db.execute(geo_sql, {"since": since})).all()
            devices_sql = text("""
                SELECT device_category,
                    SUM(sessions) AS sessions, SUM(users) AS users
                FROM raw_ga4_devices WHERE date >= :since
                GROUP BY device_category
                ORDER BY sessions DESC
            """)
            dev_rows = (await self.db.execute(devices_sql, {"since": since})).all()
        dev_total = sum(r.sessions for r in dev_rows) or 1

        # Funnel data (e-commerce events from GA4)
        has_funnel = (await self.db.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'raw_ga4_funnel')"
        ))).scalar()

        funnel_data = None
        if has_funnel:
            if focus_date is not None:
                chk = (await self.db.execute(text(
                    "SELECT COUNT(*) FROM raw_ga4_funnel WHERE date = :d AND (view_item > 0 OR add_to_cart > 0)"
                ), {"d": focus_date})).scalar() or 0
                funnel_sql = text("""
                    SELECT
                        COALESCE(SUM(view_item), 0)        AS view_item,
                        COALESCE(SUM(add_to_cart), 0)      AS add_to_cart,
                        COALESCE(SUM(begin_checkout), 0)    AS begin_checkout,
                        COALESCE(SUM(add_payment_info), 0)  AS add_payment_info,
                        COALESCE(SUM(purchase), 0)          AS purchase
                    FROM raw_ga4_funnel
                    WHERE date = :focus_date
                """)
                funnel_row = (await self.db.execute(funnel_sql, {"focus_date": focus_date})).one()
            else:
                chk = (await self.db.execute(text(
                    "SELECT COUNT(*) FROM raw_ga4_funnel WHERE date >= :s AND (view_item > 0 OR add_to_cart > 0)"
                ), {"s": since})).scalar() or 0
                funnel_sql = text("""
                    SELECT
                        COALESCE(SUM(view_item), 0)        AS view_item,
                        COALESCE(SUM(add_to_cart), 0)      AS add_to_cart,
                        COALESCE(SUM(begin_checkout), 0)    AS begin_checkout,
                        COALESCE(SUM(add_payment_info), 0)  AS add_payment_info,
                        COALESCE(SUM(purchase), 0)          AS purchase
                    FROM raw_ga4_funnel
                    WHERE date >= :since
                """)
                funnel_row = (await self.db.execute(funnel_sql, {"since": since})).one()

            if chk > 0:
                vi = int(funnel_row.view_item)
                atc = int(funnel_row.add_to_cart)
                bc = int(funnel_row.begin_checkout)
                api_val = int(funnel_row.add_payment_info)
                pur = int(funnel_row.purchase)

                funnel_data = {
                    "view_item": vi,
                    "add_to_cart": atc,
                    "begin_checkout": bc,
                    "add_payment_info": api_val,
                    "purchase": pur,
                    "add_to_cart_rate": round(atc / vi * 100, 2) if vi else 0,
                    "cart_abandonment_rate": round((1 - bc / atc) * 100, 2) if atc else 0,
                    "checkout_abandonment_rate": round((1 - api_val / bc) * 100, 2) if bc else 0,
                    "payment_to_purchase_rate": round(pur / api_val * 100, 2) if api_val else 0,
                    "overall_conversion_rate": round(pur / vi * 100, 2) if vi else 0,
                }

        sessions_total = int(ov.sessions)
        orders_total = ord_row.orders

        return {
            "has_data": True,
            "data_through": str(data_through) if data_through else None,
            "focus_date": str(focus_date) if focus_date else None,
            "overview": {
                "sessions": sessions_total,
                "users": int(ov.users),
                "new_users": int(ov.new_users),
                "bounce_rate": float(ov.bounce_rate) if ov.bounce_rate else 0,
                "avg_session_duration": float(ov.avg_duration) if ov.avg_duration else 0,
            },
            "conversion": {
                "sessions": sessions_total,
                "orders": orders_total,
                "conversion_rate": round(orders_total / sessions_total * 100, 2) if sessions_total else 0,
                "revenue": round(float(ord_row.revenue), 2),
                "revenue_per_session": round(float(ord_row.revenue) / sessions_total, 2) if sessions_total else 0,
            },
            "funnel": funnel_data,
            "time_series": [
                {
                    "date": str(r.date),
                    "sessions": r.sessions,
                    "users": r.users,
                    "orders": int(r.orders),
                    "conversion_rate": round(int(r.orders) / r.sessions * 100, 2) if r.sessions else 0,
                }
                for r in ts_rows
            ],
            "sources": [
                {
                    "source": r.source,
                    "medium": r.medium,
                    "sessions": r.sessions,
                    "users": r.users,
                    "new_users": r.new_users,
                    "engaged": r.engaged,
                    "conversions": r.conversions,
                }
                for r in src_rows
            ],
            "top_pages": [
                {
                    "page_path": r.page_path,
                    "views": r.views,
                    "avg_time": float(r.avg_time) if r.avg_time else 0,
                    "entrances": r.entrances,
                }
                for r in page_rows
            ],
            "geo": [
                {"country": r.country, "city": r.city, "sessions": r.sessions, "users": r.users}
                for r in geo_rows
            ],
            "devices": [
                {
                    "device_category": r.device_category,
                    "sessions": r.sessions,
                    "users": r.users,
                    "pct": round(r.sessions / dev_total * 100, 1),
                }
                for r in dev_rows
            ],
        }
