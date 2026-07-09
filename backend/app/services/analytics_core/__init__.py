"""CORE star-schema analytics (fact_*, dim_*)."""

from .cohorts import CohortsService
from .customers_analytics import CustomersAnalyticsService
from .overview import OverviewService
from .revenue import RevenueService
from .top_products import TopProductsService
from .trends import TrendsService

__all__ = [
    "CohortsService",
    "CustomersAnalyticsService",
    "OverviewService",
    "RevenueService",
    "TopProductsService",
    "TrendsService",
]
