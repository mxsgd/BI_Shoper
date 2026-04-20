"""
GA4 Data API client — pulls analytics reports into raw_ga4_* tables.

Uses google-analytics-data (v1beta) with a service account.
Set GA4_PROPERTY_ID and GA4_CREDENTIALS_PATH in .env.
"""

import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..config import get_settings

logger = logging.getLogger(__name__)


def _get_ga4_client():
    """Lazy import so the app starts even without the google package installed."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, FilterExpression, Filter,
    )

    settings = get_settings()
    if not settings.ga4_property_id or not settings.ga4_credentials_path:
        return None, None, None, None, None, None, None, None

    client = BetaAnalyticsDataClient.from_service_account_json(
        settings.ga4_credentials_path
    )
    property_id = f"properties/{settings.ga4_property_id}"
    return client, property_id, RunReportRequest, DateRange, Dimension, Metric, FilterExpression, Filter


_STORE_PAGE_FILTER = None

def _get_store_filter(FilterExpression, Filter):
    """Only count sessions that visited /pl/ pages (exclude BI dashboard, old URLs)."""
    global _STORE_PAGE_FILTER
    if _STORE_PAGE_FILTER is None:
        _STORE_PAGE_FILTER = FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.BEGINS_WITH,
                    value="/pl/",
                ),
            )
        )
    return _STORE_PAGE_FILTER


def _run_report(client, property_id, RunReportRequest, DateRange, Dimension, Metric,
                FilterExpression, Filter,
                date_str: str, dimensions: list[str], metrics: list[str]):
    request = RunReportRequest(
        property=property_id,
        date_ranges=[DateRange(start_date=date_str, end_date=date_str)],
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        dimension_filter=_get_store_filter(FilterExpression, Filter),
        limit=10000,
    )
    return client.run_report(request)


def _val(row, idx: int, is_int=False):
    v = row.metric_values[idx].value
    if is_int:
        return int(float(v))
    return float(v)


def _dim(row, idx: int):
    return row.dimension_values[idx].value


class GA4SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _sync_part(self, counts: dict, errors: dict, key: str, coro):
        try:
            counts[key] = await coro
        except Exception as exc:
            logger.warning("GA4 sync part '%s' failed: %s", key, exc)
            counts[key] = 0
            errors[key] = str(exc)

    async def sync_day(self, target_date: date) -> dict:
        """Pull all GA4 reports for a single day and upsert into raw tables."""
        parts = _get_ga4_client()
        if parts[0] is None:
            logger.warning("GA4 not configured (GA4_PROPERTY_ID / GA4_CREDENTIALS_PATH missing)")
            return {"ok": False, "reason": "ga4_not_configured"}

        client, property_id, RunReportRequest, DateRange, Dimension, Metric, FilterExpression, Filter = parts
        date_str = target_date.isoformat()
        counts = {}
        errors = {}

        api = (client, property_id, RunReportRequest, DateRange, Dimension, Metric, FilterExpression, Filter)
        await self._sync_part(counts, errors, "traffic", self._sync_traffic(*api, date_str, target_date))
        await self._sync_part(counts, errors, "sources", self._sync_sources(*api, date_str, target_date))
        await self._sync_part(counts, errors, "pages", self._sync_pages(*api, date_str, target_date))
        await self._sync_part(counts, errors, "geo", self._sync_geo(*api, date_str, target_date))
        await self._sync_part(counts, errors, "devices", self._sync_devices(*api, date_str, target_date))
        await self._sync_part(counts, errors, "funnel", self._sync_funnel(*api, date_str, target_date))
        await self._sync_part(counts, errors, "funnel_devices", self._sync_funnel_devices(*api, date_str, target_date))

        if errors:
            logger.warning("GA4 sync for %s completed with errors: %s", date_str, errors)
        else:
            logger.info("GA4 sync for %s: %s", date_str, counts)
        return {"ok": True, "date": date_str, "errors": errors, **counts}

    async def backfill(self, days: int = 90) -> dict:
        """Pull historical GA4 data when tables are empty."""
        result = await self.db.execute(text("SELECT COUNT(*) FROM raw_ga4_traffic"))
        if (result.scalar() or 0) > 0:
            return {"ok": True, "skipped": True, "reason": "data_exists"}

        results = []
        for i in range(days, 0, -1):
            d = date.today() - timedelta(days=i)
            r = await self.sync_day(d)
            results.append(r)
        return {"ok": True, "days_synced": len(results)}

    async def _sync_traffic(self, client, property_id, RunReportRequest, DateRange, Dimension, Metric,
                            FilterExpression, Filter, date_str, target_date):
        response = _run_report(
            client, property_id, RunReportRequest, DateRange, Dimension, Metric,
            FilterExpression, Filter,
            date_str, dimensions=[], metrics=[
                "sessions", "totalUsers", "newUsers", "screenPageViews",
                "bounceRate", "averageSessionDuration", "engagedSessions", "eventCount",
            ]
        )
        if not response.rows:
            return 0
        row = response.rows[0]
        sql = text("""
            INSERT INTO raw_ga4_traffic (date, sessions, total_users, new_users, page_views,
                bounce_rate, avg_session_duration, engaged_sessions, events_count)
            VALUES (:date, :sessions, :total_users, :new_users, :page_views,
                :bounce_rate, :avg_session_duration, :engaged_sessions, :events_count)
            ON CONFLICT (date) DO UPDATE SET
                sessions = EXCLUDED.sessions, total_users = EXCLUDED.total_users,
                new_users = EXCLUDED.new_users, page_views = EXCLUDED.page_views,
                bounce_rate = EXCLUDED.bounce_rate, avg_session_duration = EXCLUDED.avg_session_duration,
                engaged_sessions = EXCLUDED.engaged_sessions, events_count = EXCLUDED.events_count
        """)
        await self.db.execute(sql, {
            "date": target_date,
            "sessions": _val(row, 0, True), "total_users": _val(row, 1, True),
            "new_users": _val(row, 2, True), "page_views": _val(row, 3, True),
            "bounce_rate": _val(row, 4), "avg_session_duration": _val(row, 5),
            "engaged_sessions": _val(row, 6, True), "events_count": _val(row, 7, True),
        })
        await self.db.commit()
        return 1

    async def _sync_sources(self, client, property_id, RunReportRequest, DateRange, Dimension, Metric,
                            FilterExpression, Filter, date_str, target_date):
        response = _run_report(
            client, property_id, RunReportRequest, DateRange, Dimension, Metric,
            FilterExpression, Filter, date_str,
            dimensions=["sessionSource", "sessionMedium", "sessionCampaignName"],
            metrics=["sessions", "totalUsers", "newUsers", "engagedSessions", "conversions"],
        )
        count = 0
        sql = text("""
            INSERT INTO raw_ga4_sources (date, source, medium, campaign,
                sessions, users, new_users, engaged_sessions, conversions, revenue)
            VALUES (:date, :source, :medium, :campaign,
                :sessions, :users, :new_users, :engaged_sessions, :conversions, 0)
            ON CONFLICT (date, source, medium) DO UPDATE SET
                campaign = EXCLUDED.campaign,
                sessions = EXCLUDED.sessions, users = EXCLUDED.users,
                new_users = EXCLUDED.new_users, engaged_sessions = EXCLUDED.engaged_sessions,
                conversions = EXCLUDED.conversions
        """)
        for row in response.rows:
            await self.db.execute(sql, {
                "date": target_date,
                "source": _dim(row, 0), "medium": _dim(row, 1), "campaign": _dim(row, 2),
                "sessions": _val(row, 0, True), "users": _val(row, 1, True),
                "new_users": _val(row, 2, True), "engaged_sessions": _val(row, 3, True),
                "conversions": _val(row, 4, True),
            })
            count += 1
        await self.db.commit()
        return count

    async def _sync_pages(self, client, property_id, RunReportRequest, DateRange, Dimension, Metric,
                          FilterExpression, Filter, date_str, target_date):
        response = _run_report(
            client, property_id, RunReportRequest, DateRange, Dimension, Metric,
            FilterExpression, Filter, date_str,
            dimensions=["pagePath", "pageTitle"],
            metrics=["screenPageViews", "averageSessionDuration", "sessions"],
        )
        count = 0
        sql = text("""
            INSERT INTO raw_ga4_pages (date, page_path, page_title, page_views,
                avg_time_on_page, entrances, exits, bounce_rate)
            VALUES (:date, :page_path, :page_title, :page_views,
                :avg_time_on_page, :entrances, 0, 0)
            ON CONFLICT (date, page_path) DO UPDATE SET
                page_title = EXCLUDED.page_title,
                page_views = EXCLUDED.page_views, avg_time_on_page = EXCLUDED.avg_time_on_page,
                entrances = EXCLUDED.entrances
        """)
        for row in response.rows:
            page_path = _dim(row, 0)
            if not page_path.startswith("/pl/"):
                continue
            await self.db.execute(sql, {
                "date": target_date,
                "page_path": page_path, "page_title": _dim(row, 1),
                "page_views": _val(row, 0, True), "avg_time_on_page": _val(row, 1),
                "entrances": _val(row, 2, True),
            })
            count += 1
        await self.db.commit()
        return count

    async def _sync_geo(self, client, property_id, RunReportRequest, DateRange, Dimension, Metric,
                        FilterExpression, Filter, date_str, target_date):
        response = _run_report(
            client, property_id, RunReportRequest, DateRange, Dimension, Metric,
            FilterExpression, Filter, date_str,
            dimensions=["country", "city"],
            metrics=["sessions", "totalUsers", "newUsers"],
        )
        count = 0
        sql = text("""
            INSERT INTO raw_ga4_geo (date, country, city, sessions, users, new_users)
            VALUES (:date, :country, :city, :sessions, :users, :new_users)
            ON CONFLICT (date, country, city) DO UPDATE SET
                sessions = EXCLUDED.sessions, users = EXCLUDED.users, new_users = EXCLUDED.new_users
        """)
        for row in response.rows:
            await self.db.execute(sql, {
                "date": target_date,
                "country": _dim(row, 0), "city": _dim(row, 1),
                "sessions": _val(row, 0, True), "users": _val(row, 1, True),
                "new_users": _val(row, 2, True),
            })
            count += 1
        await self.db.commit()
        return count

    async def _sync_devices(self, client, property_id, RunReportRequest, DateRange, Dimension, Metric,
                            FilterExpression, Filter, date_str, target_date):
        response = _run_report(
            client, property_id, RunReportRequest, DateRange, Dimension, Metric,
            FilterExpression, Filter, date_str,
            dimensions=["deviceCategory", "browser", "operatingSystem"],
            metrics=["sessions", "totalUsers"],
        )
        count = 0
        sql = text("""
            INSERT INTO raw_ga4_devices (date, device_category, browser, os, sessions, users)
            VALUES (:date, :device_category, :browser, :os, :sessions, :users)
            ON CONFLICT (date, device_category, browser, os) DO UPDATE SET
                sessions = EXCLUDED.sessions, users = EXCLUDED.users
        """)
        for row in response.rows:
            await self.db.execute(sql, {
                "date": target_date,
                "device_category": _dim(row, 0), "browser": _dim(row, 1), "os": _dim(row, 2),
                "sessions": _val(row, 0, True), "users": _val(row, 1, True),
            })
            count += 1
        await self.db.commit()
        return count

    _FUNNEL_EVENTS = (
        "view_item", "add_to_cart", "begin_checkout",
        "add_payment_info", "purchase", "remove_from_cart",
    )

    async def _sync_funnel(self, client, property_id, RunReportRequest, DateRange, Dimension, Metric,
                           FilterExpression, Filter, date_str, target_date):
        response = _run_report(
            client, property_id, RunReportRequest, DateRange, Dimension, Metric,
            FilterExpression, Filter, date_str,
            dimensions=["eventName"],
            metrics=["eventCount", "eventValue"],
        )
        counts = {e: 0 for e in self._FUNNEL_EVENTS}
        values = {e: 0.0 for e in self._FUNNEL_EVENTS}
        for row in response.rows:
            name = _dim(row, 0)
            if name in counts:
                counts[name] = _val(row, 0, True)
                values[name] = _val(row, 1)

        sql = text("""
            INSERT INTO raw_ga4_funnel
                (date, view_item, add_to_cart, begin_checkout, add_payment_info,
                 purchase, remove_from_cart, add_to_cart_value, purchase_value)
            VALUES
                (:date, :view_item, :add_to_cart, :begin_checkout, :add_payment_info,
                 :purchase, :remove_from_cart, :add_to_cart_value, :purchase_value)
            ON CONFLICT (date) DO UPDATE SET
                view_item = EXCLUDED.view_item, add_to_cart = EXCLUDED.add_to_cart,
                begin_checkout = EXCLUDED.begin_checkout, add_payment_info = EXCLUDED.add_payment_info,
                purchase = EXCLUDED.purchase, remove_from_cart = EXCLUDED.remove_from_cart,
                add_to_cart_value = EXCLUDED.add_to_cart_value, purchase_value = EXCLUDED.purchase_value
        """)
        await self.db.execute(sql, {
            "date": target_date,
            **counts,
            "add_to_cart_value": values["add_to_cart"],
            "purchase_value": values["purchase"],
        })
        await self.db.commit()
        return 1

    async def _sync_funnel_devices(self, client, property_id, RunReportRequest, DateRange, Dimension, Metric,
                                   FilterExpression, Filter, date_str, target_date):
        response = _run_report(
            client, property_id, RunReportRequest, DateRange, Dimension, Metric,
            FilterExpression, Filter, date_str,
            dimensions=["eventName", "deviceCategory"],
            metrics=["eventCount"],
        )
        device_data: dict[str, dict[str, int]] = {}
        for row in response.rows:
            event_name = _dim(row, 0)
            if event_name not in self._FUNNEL_EVENTS:
                continue
            device = _dim(row, 1)
            if device not in device_data:
                device_data[device] = {e: 0 for e in self._FUNNEL_EVENTS}
            device_data[device][event_name] = _val(row, 0, True)

        sql = text("""
            INSERT INTO raw_ga4_funnel_devices
                (date, device_category, view_item, add_to_cart, begin_checkout,
                 add_payment_info, purchase, remove_from_cart)
            VALUES
                (:date, :device_category, :view_item, :add_to_cart, :begin_checkout,
                 :add_payment_info, :purchase, :remove_from_cart)
            ON CONFLICT (date, device_category) DO UPDATE SET
                view_item = EXCLUDED.view_item, add_to_cart = EXCLUDED.add_to_cart,
                begin_checkout = EXCLUDED.begin_checkout, add_payment_info = EXCLUDED.add_payment_info,
                purchase = EXCLUDED.purchase, remove_from_cart = EXCLUDED.remove_from_cart
        """)
        count = 0
        for device, events in device_data.items():
            await self.db.execute(sql, {"date": target_date, "device_category": device, **events})
            count += 1
        await self.db.commit()
        return count

