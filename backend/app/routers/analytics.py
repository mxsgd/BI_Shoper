"""
Analytics API — CORE star-schema endpoints.

All queries hit the CORE layer (fact_orders, fact_order_items, dim_*).
Query params: store_id (required), period (days, default 30),
            compare (bool — include previous period for comparison).
"""

from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.analytics_core.common import (
    FocusDateOutOfPeriodError,
    date_bucket_series_sql as _date_bucket_series_sql,
)
from ..services.analytics_core.cohorts import CohortsService
from ..services.analytics_core.customers_analytics import CustomersAnalyticsService
from ..services.analytics_core.overview import OverviewService
from ..services.analytics_core.revenue import RevenueService
from ..services.analytics_core.top_products import TopProductsService
from ..services.analytics_core.trends import TrendsService
from ..services.analytics_core.rfm import RfmService
from ..services.analytics_core.channels import ChannelsService
from ..services.analytics_core.traffic import TrafficService
from ..services.analytics_core.cart import CartService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ──────────────────────────────────────────────────────────────────
# GET /analytics/overview
# ──────────────────────────────────────────────────────────────────
@router.get("/overview")
async def overview(
    store_id: int = Query(...),
    period: int = Query(30, ge=1, le=365),
    focus_date: Optional[date] = Query(None, description="Single day; KPIs for this day vs previous day"),
    db: AsyncSession = Depends(get_db),
):
    """
    KPI summary cards: revenue, order count, AOV, unique customers,
    avg items/order, paid %, with comparison to previous period.
    With focus_date: metrics for that day only (delta vs previous calendar day).
    """
    svc = OverviewService(db)
    try:
        return await svc.get_overview(store_id, period, focus_date)
    except FocusDateOutOfPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ──────────────────────────────────────────────────────────────────
# GET /analytics/revenue
# ──────────────────────────────────────────────────────────────────
@router.get("/revenue")
async def revenue(
    store_id: int = Query(...),
    period: int = Query(30, ge=1, le=365),
    group_by: Literal["day", "week", "month"] = Query("day"),
    focus_date: Optional[date] = Query(None, description="Scope by_status/by_channel/by_category to this day"),
    db: AsyncSession = Depends(get_db),
):
    """
    Revenue time series + breakdown by status and channel.
    With focus_date: status/channel tables are for that day only (time_series unchanged).
    """
    svc = RevenueService(db)
    try:
        return await svc.get_revenue(store_id, period, group_by, focus_date)
    except FocusDateOutOfPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ──────────────────────────────────────────────────────────────────
# GET /analytics/top-products
# ──────────────────────────────────────────────────────────────────
@router.get("/top-products")
async def top_products(
    store_id: int = Query(...),
    period: int = Query(90, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    sort_by: Literal["revenue", "quantity"] = Query("revenue"),
    db: AsyncSession = Depends(get_db),
):
    """
    Top products by revenue or quantity, with Pareto cumulative %.
    """
    svc = TopProductsService(db)
    return await svc.get_top_products(store_id, period, limit, sort_by)


# ──────────────────────────────────────────────────────────────────
# GET /analytics/customers
# ──────────────────────────────────────────────────────────────────
@router.get("/customers")
async def customers_analytics(
    store_id: int = Query(...),
    period: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Customer analytics: new vs returning, top by revenue, cohort overview.
    """
    svc = CustomersAnalyticsService(db)
    return await svc.get_customers_analytics(store_id, period)


# ──────────────────────────────────────────────────────────────────
# GET /analytics/trends
# ──────────────────────────────────────────────────────────────────
@router.get("/trends")
async def trends(
    store_id: int = Query(...),
    period: int = Query(365, ge=30, le=730),
    db: AsyncSession = Depends(get_db),
):
    """
    Sales trends: daily with MA7/MA30, monthly MoM/YoY, weekday patterns.
    """
    svc = TrendsService(db)
    return await svc.get_trends(store_id, period)


# ──────────────────────────────────────────────────────────────────
# GET /analytics/cohorts
# ──────────────────────────────────────────────────────────────────
@router.get("/cohorts")
async def cohorts(
    store_id: int = Query(...),
    months: int = Query(12, ge=3, le=24),
    db: AsyncSession = Depends(get_db),
):
    """
    Monthly acquisition cohort retention matrix.
    """
    svc = CohortsService(db)
    return await svc.get_cohorts(store_id, months)


# ──────────────────────────────────────────────────────────────────
# GET /analytics/rfm
# ──────────────────────────────────────────────────────────────────
@router.get("/rfm")
async def rfm_analysis(
    store_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    RFM scoring with segment breakdown and CLV summary.
    """
    svc = RfmService(db)
    return await svc.get_rfm(store_id)


# ──────────────────────────────────────────────────────────────────
# GET /analytics/channels
# ──────────────────────────────────────────────────────────────────
@router.get("/channels")
async def channels(
    store_id: int = Query(...),
    period: int = Query(90, ge=1, le=365),
    group_by: Literal["day", "week", "month"] = Query("month"),
    db: AsyncSession = Depends(get_db),
):
    """
    Channel breakdown over time with summary.
    """
    svc = ChannelsService(db)
    return await svc.get_channels(store_id, period, group_by)


# ──────────────────────────────────────────────────────────────────
# GET /analytics/traffic  (GA4 data + conversion from Shoper)
# ──────────────────────────────────────────────────────────────────
@router.get("/traffic")
async def traffic(
    store_id: int = Query(...),
    period: int = Query(30, ge=1, le=365),
    focus_date: Optional[date] = Query(None, description="KPIs/tables for this day only; time_series unchanged"),
    db: AsyncSession = Depends(get_db),
):
    """
    GA4 traffic overview joined with Shoper orders for conversion analysis.
    Returns empty structures gracefully if GA4 tables have no data.
    With focus_date: overview, conversion, sources, pages, geo, devices scoped to that day.
    """
    svc = TrafficService(db)
    return await svc.get_traffic(store_id, period, focus_date)


# ──────────────────────────────────────────────────────────────────
# GET /analytics/cart
# ──────────────────────────────────────────────────────────────────

@router.get("/cart")
async def cart_analysis(
    store_id: int = Query(...),
    period: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Cart & funnel deep-dive: KPIs, funnel visualization, device segmentation,
    product-level drop-off, and order-based cart metrics from Shoper.
    """
    svc = CartService(db)
    return await svc.get_cart(store_id, period)


# ──────────────────────────────────────────────────────────────────
# GET /analytics/tracker
# ──────────────────────────────────────────────────────────────────
@router.get("/tracker")
async def tracker_events_summary(
    store_id: int = Query(...),
    period: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Prosty podgląd trackera (lokalna tabela tracker_events_local) — liczba eventów
    wg typu oraz unikalni użytkownicy w ostatnich N dniach.

    Uwaga: tracker nie jest powiązany ze store_id (na razie globalny); parametr jest
    przyjmowany tylko dla spójności API.
    """
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
