"""Every analytics service runs against the seeded store, with and without a focus day.

These catch runtime SQL mistakes that unit-level checks miss - e.g. a mistyped column in the
focus-day branch of the traffic query, which returned HTTP 500 whenever a day was clicked.
"""
from datetime import date, timedelta

import pytest

from app.services.analytics_core.cart import CartService
from app.services.analytics_core.channels import ChannelsService
from app.services.analytics_core.cohorts import CohortsService
from app.services.analytics_core.customers_analytics import CustomersAnalyticsService
from app.services.analytics_core.overview import OverviewService
from app.services.analytics_core.revenue import RevenueService
from app.services.analytics_core.rfm import RfmService
from app.services.analytics_core.top_products import TopProductsService
from app.services.analytics_core.tracker import TrackerService
from app.services.analytics_core.traffic import TrafficService
from app.services.analytics_core.trends import TrendsService

FOCUS = date.today() - timedelta(days=3)  # services measure periods back from today

CASES = {
    "overview": lambda s: OverviewService(s).get_overview(1, 30, None),
    "overview_focus_day": lambda s: OverviewService(s).get_overview(1, 30, FOCUS),
    "revenue_day": lambda s: RevenueService(s).get_revenue(1, 30, "day", None),
    "revenue_week": lambda s: RevenueService(s).get_revenue(1, 90, "week", None),
    "revenue_month": lambda s: RevenueService(s).get_revenue(1, 365, "month", None),
    "revenue_focus_day": lambda s: RevenueService(s).get_revenue(1, 30, "day", FOCUS),
    "top_products": lambda s: TopProductsService(s).get_top_products(1, 90, 20, "revenue"),
    "customers": lambda s: CustomersAnalyticsService(s).get_customers_analytics(1, 90),
    "trends": lambda s: TrendsService(s).get_trends(1, 365),
    "cohorts": lambda s: CohortsService(s).get_cohorts(1, 12),
    "rfm": lambda s: RfmService(s).get_rfm(1),
    "channels": lambda s: ChannelsService(s).get_channels(1, 90, "month"),
    "traffic": lambda s: TrafficService(s).get_traffic(1, 30, None),
    "traffic_focus_day": lambda s: TrafficService(s).get_traffic(1, 30, FOCUS),
    "cart": lambda s: CartService(s).get_cart(1, 30),
    "tracker": lambda s: TrackerService(s).tracker_events_summary(1, 7),
}


@pytest.mark.parametrize("name", CASES)
async def test_analytics_service_runs(session, name):
    result = await CASES[name](session)
    assert isinstance(result, dict) and result
