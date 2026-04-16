"""
Analytics API — CORE star-schema endpoints.

All queries hit the CORE layer (fact_orders, fact_order_items, dim_*).
Query params: store_id (required), period (days, default 30),
              compare (bool — include previous period for comparison).
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _date_bucket_series_sql(group_by: Literal["day", "week", "month"]) -> str:
    """SQL fragment: FROM ... AS b(bucket) producing one row per bucket in the period.

    Use CAST(:x AS type), not :x::type — SQLAlchemy treats ':' as bind syntax and breaks on '::'.
    """
    if group_by == "day":
        return (
            "generate_series(CAST(:since AS date), CAST(:today AS date), interval '1 day') "
            "AS b(bucket)"
        )
    if group_by == "week":
        return (
            "generate_series("
            "date_trunc('week', CAST(:since AS timestamp))::date, "
            "date_trunc('week', CAST(:today AS timestamp))::date, "
            "interval '1 week'"
            ") AS b(bucket)"
        )
    return (
        "generate_series("
        "date_trunc('month', CAST(:since AS date))::date, "
        "date_trunc('month', CAST(:today AS date))::date, "
        "interval '1 month'"
        ") AS b(bucket)"
    )


def _period_bounds(period_days: int) -> tuple[date, date, date, date]:
    """Return (cur_start, cur_end, prev_start, prev_end) for current + previous period."""
    today = date.today()
    cur_end = today
    cur_start = today - timedelta(days=period_days - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_days - 1)
    return cur_start, cur_end, prev_start, prev_end


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
    cur_start, cur_end, prev_start, prev_end = _period_bounds(period)

    def _delta(cur_val, prev_val):
        if not prev_val:
            return None
        return round((float(cur_val) - float(prev_val)) / float(prev_val) * 100, 1)

    if focus_date is not None:
        if focus_date < cur_start or focus_date > cur_end:
            raise HTTPException(status_code=400, detail="focus_date outside selected period")
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
        row = (await db.execute(sql, {
            "store_id": store_id,
            "focus_date": focus_date,
            "prev_day": prev_day,
        })).one()
        return {
            "period_days": period,
            "focus_date": str(focus_date),
            "date_from": str(focus_date),
            "date_to": str(focus_date),
            "revenue": round(float(row.revenue), 2),
            "revenue_delta_pct": _delta(row.revenue, row.prev_revenue),
            "orders": row.orders,
            "orders_delta_pct": _delta(row.orders, row.prev_orders),
            "aov": round(float(row.aov), 2),
            "aov_delta_pct": _delta(row.aov, row.prev_aov),
            "customers": row.customers,
            "customers_delta_pct": _delta(row.customers, row.prev_customers),
            "avg_items_per_order": round(float(row.avg_items), 1),
            "paid_pct": round(row.paid_orders / row.orders * 100, 1) if row.orders else 0,
        }

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

    row = (await db.execute(sql, {
        "store_id": store_id,
        "cur_start": cur_start, "cur_end": cur_end,
        "prev_start": prev_start, "prev_end": prev_end,
    })).one()

    return {
        "period_days": period,
        "focus_date": None,
        "date_from": str(cur_start),
        "date_to": str(cur_end),
        "revenue": round(float(row.revenue), 2),
        "revenue_delta_pct": _delta(row.revenue, row.prev_revenue),
        "orders": row.orders,
        "orders_delta_pct": _delta(row.orders, row.prev_orders),
        "aov": round(float(row.aov), 2),
        "aov_delta_pct": _delta(row.aov, row.prev_aov),
        "customers": row.customers,
        "customers_delta_pct": _delta(row.customers, row.prev_customers),
        "avg_items_per_order": round(float(row.avg_items), 1),
        "paid_pct": round(row.paid_orders / row.orders * 100, 1) if row.orders else 0,
    }


# ──────────────────────────────────────────────────────────────────
# GET /analytics/revenue
# ──────────────────────────────────────────────────────────────────
@router.get("/revenue")
async def revenue(
    store_id: int = Query(...),
    period: int = Query(30, ge=1, le=365),
    group_by: Literal["day", "week", "month"] = Query("day"),
    focus_date: Optional[date] = Query(None, description="Scope by_status/by_channel to this day"),
    db: AsyncSession = Depends(get_db),
):
    """
    Revenue time series + breakdown by status and channel.
    With focus_date: status/channel tables are for that day only (time_series unchanged).
    """
    cur_start = date.today() - timedelta(days=period - 1)
    today = date.today()
    if focus_date is not None and (focus_date < cur_start or focus_date > today):
        raise HTTPException(status_code=400, detail="focus_date outside selected period")

    trunc_map = {"day": "day", "week": "week", "month": "month"}
    trunc = trunc_map[group_by]
    bucket_from = _date_bucket_series_sql(group_by)

    # Time series — full calendar buckets (zeros where no orders)
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
    ts_rows = (await db.execute(ts_sql, {
        "store_id": store_id, "since": cur_start, "today": today, "trunc": trunc,
    })).all()

    # By status / channel — whole period, or single day when focus_date set
    if focus_date is not None:
        status_sql = text("""
            SELECT order_status, COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date = :focus_date
            GROUP BY order_status
            ORDER BY revenue DESC
        """)
        status_rows = (await db.execute(status_sql, {
            "store_id": store_id, "focus_date": focus_date,
        })).all()
        channel_sql = text("""
            SELECT source_channel, COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date = :focus_date
            GROUP BY source_channel
            ORDER BY revenue DESC
        """)
        channel_rows = (await db.execute(channel_sql, {
            "store_id": store_id, "focus_date": focus_date,
        })).all()
    else:
        status_sql = text("""
            SELECT order_status, COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date >= :since
            GROUP BY order_status
            ORDER BY revenue DESC
        """)
        status_rows = (await db.execute(status_sql, {
            "store_id": store_id, "since": cur_start,
        })).all()
        channel_sql = text("""
            SELECT source_channel, COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date >= :since
            GROUP BY source_channel
            ORDER BY revenue DESC
        """)
        channel_rows = (await db.execute(channel_sql, {
            "store_id": store_id, "since": cur_start,
        })).all()

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
            {"status": r.order_status, "orders": r.orders, "revenue": round(float(r.revenue), 2)}
            for r in status_rows
        ],
        "by_channel": [
            {"channel": r.source_channel, "orders": r.orders, "revenue": round(float(r.revenue), 2)}
            for r in channel_rows
        ],
    }


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
    since = date.today() - timedelta(days=period - 1)
    order_col = "revenue" if sort_by == "revenue" else "total_qty"

    sql = text(f"""
        WITH ranked AS (
            SELECT
                foi.product_id,
                dp.product_name,
                dc.category_name,
                SUM(foi.quantity)    AS total_qty,
                SUM(foi.total_gross) AS revenue,
                COUNT(DISTINCT foi.order_id) AS order_count
            FROM fact_order_items foi
            JOIN fact_orders fo
                ON fo.order_id = foi.order_id
            LEFT JOIN dim_products dp
                ON dp.product_id = foi.product_id
            LEFT JOIN dim_categories dc
                ON dc.category_id = foi.category_id
            WHERE fo.store_id = :store_id
              AND fo.order_date::date >= :since
            GROUP BY foi.product_id, dp.product_name, dc.category_name
        ),
        totals AS (
            SELECT SUM(revenue) AS grand_total FROM ranked
        )
        SELECT
            r.product_id,
            r.product_name,
            r.category_name,
            r.total_qty,
            r.revenue,
            r.order_count,
            ROUND(r.revenue / NULLIF(t.grand_total, 0) * 100, 2) AS revenue_pct,
            SUM(r.revenue) OVER (ORDER BY r.{order_col} DESC)
                / NULLIF(t.grand_total, 0) * 100 AS cumulative_pct
        FROM ranked r, totals t
        ORDER BY r.{order_col} DESC
        LIMIT :lim
    """)

    rows = (await db.execute(sql, {
        "store_id": store_id, "since": since, "lim": limit,
    })).all()

    return {
        "period_days": period,
        "sort_by": sort_by,
        "products": [
            {
                "product_id": r.product_id,
                "name": r.product_name or f"Product #{r.product_id}",
                "category": r.category_name,
                "quantity": int(r.total_qty),
                "revenue": round(float(r.revenue), 2),
                "orders": r.order_count,
                "revenue_pct": float(r.revenue_pct or 0),
                "cumulative_pct": round(float(r.cumulative_pct or 0), 2),
            }
            for r in rows
        ],
    }


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
    since = date.today() - timedelta(days=period - 1)
    today = date.today()

    # Segmentation
    seg_sql = text("""
        SELECT
            customer_type,
            COUNT(*)                           AS count,
            COALESCE(SUM(total_revenue), 0)    AS revenue,
            COALESCE(AVG(total_orders), 0)     AS avg_orders,
            COALESCE(AVG(total_revenue), 0)    AS avg_revenue
        FROM dim_customers
        WHERE store_id = :store_id
        GROUP BY customer_type
    """)
    seg_rows = (await db.execute(seg_sql, {"store_id": store_id})).all()

    # Top customers by revenue
    top_sql = text("""
        SELECT
            dc.customer_id,
            dc.total_orders,
            dc.total_revenue,
            dc.first_order_date,
            dc.last_order_date,
            dc.customer_type
        FROM dim_customers dc
        WHERE dc.store_id = :store_id AND dc.total_revenue > 0
        ORDER BY dc.total_revenue DESC
        LIMIT 20
    """)
    top_rows = (await db.execute(top_sql, {"store_id": store_id})).all()

    # New customers per month — full month range (zeros where none)
    new_sql = text("""
        SELECT
            d.month::date AS month,
            COALESCE(agg.new_customers, 0) AS new_customers
        FROM generate_series(
            date_trunc('month', CAST(:since AS date))::date,
            date_trunc('month', CAST(:today AS date))::date,
            interval '1 month'
        ) AS d(month)
        LEFT JOIN (
            SELECT
                date_trunc('month', first_order_date)::date AS month,
                COUNT(*) AS new_customers
            FROM dim_customers
            WHERE store_id = :store_id
              AND first_order_date IS NOT NULL
              AND first_order_date::date >= :since
            GROUP BY month
        ) agg ON agg.month = d.month::date
        ORDER BY d.month
    """)
    new_rows = (await db.execute(new_sql, {
        "store_id": store_id, "since": since, "today": today,
    })).all()

    # Repeat rate
    repeat_sql = text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE total_orders > 1) AS repeat_buyers,
            COUNT(*) FILTER (WHERE total_orders = 1) AS one_time
        FROM dim_customers
        WHERE store_id = :store_id AND total_orders > 0
    """)
    repeat_row = (await db.execute(repeat_sql, {"store_id": store_id})).one()

    return {
        "period_days": period,
        "segmentation": [
            {
                "type": r.customer_type,
                "count": r.count,
                "revenue": round(float(r.revenue), 2),
                "avg_orders": round(float(r.avg_orders), 1),
                "avg_revenue": round(float(r.avg_revenue), 2),
            }
            for r in seg_rows
        ],
        "top_customers": [
            {
                "customer_id": r.customer_id,
                "total_orders": r.total_orders,
                "total_revenue": round(float(r.total_revenue), 2),
                "first_order": str(r.first_order_date.date()) if r.first_order_date else None,
                "last_order": str(r.last_order_date.date()) if r.last_order_date else None,
                "type": r.customer_type,
            }
            for r in top_rows
        ],
        "new_customers_monthly": [
            {"month": str(r.month), "count": r.new_customers}
            for r in new_rows
        ],
        "retention": {
            "total_buyers": repeat_row.total,
            "repeat_buyers": repeat_row.repeat_buyers,
            "one_time_buyers": repeat_row.one_time,
            "repeat_rate_pct": round(
                repeat_row.repeat_buyers / repeat_row.total * 100, 1
            ) if repeat_row.total else 0,
        },
    }


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
    since = date.today() - timedelta(days=period - 1)

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
    daily_rows = (await db.execute(daily_sql, {
        "store_id": store_id, "since": since, "today": date.today(),
    })).all()

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
    monthly_rows = (await db.execute(monthly_sql, {"store_id": store_id})).all()

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
    weekday_rows = (await db.execute(weekday_sql, {
        "store_id": store_id, "since": since,
    })).all()

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
    since = date.today() - timedelta(days=months * 31)

    sql = text("""
        WITH cohorts AS (
            SELECT customer_id,
                   date_trunc('month', first_order_date)::date AS cohort_month
            FROM dim_customers
            WHERE store_id = :store_id
              AND first_order_date IS NOT NULL
              AND first_order_date::date >= :since
        ),
        cohort_sizes AS (
            SELECT cohort_month, COUNT(*) AS size
            FROM cohorts GROUP BY cohort_month
        ),
        activity AS (
            SELECT DISTINCT fo.customer_id,
                   date_trunc('month', fo.order_date)::date AS activity_month
            FROM fact_orders fo
            WHERE fo.store_id = :store_id AND fo.customer_id IS NOT NULL
        ),
        matrix AS (
            SELECT
                c.cohort_month,
                (EXTRACT(YEAR FROM a.activity_month) - EXTRACT(YEAR FROM c.cohort_month)) * 12
                + EXTRACT(MONTH FROM a.activity_month) - EXTRACT(MONTH FROM c.cohort_month)
                AS month_offset,
                COUNT(DISTINCT a.customer_id) AS active
            FROM cohorts c
            JOIN activity a ON a.customer_id = c.customer_id
                           AND a.activity_month >= c.cohort_month
            GROUP BY c.cohort_month, month_offset
        )
        SELECT m.cohort_month, cs.size, m.month_offset, m.active
        FROM matrix m
        JOIN cohort_sizes cs ON cs.cohort_month = m.cohort_month
        ORDER BY m.cohort_month, m.month_offset
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "since": since})).all()

    cohort_map: dict[str, dict] = {}
    for r in rows:
        key = str(r.cohort_month)
        if key not in cohort_map:
            cohort_map[key] = {"cohort_month": key, "size": r.size, "months": []}
        cohort_map[key]["months"].append({
            "month_offset": int(r.month_offset),
            "active": r.active,
            "retention_pct": round(r.active / r.size * 100, 1) if r.size else 0,
        })

    return {"cohorts": list(cohort_map.values())}


# ──────────────────────────────────────────────────────────────────
# GET /analytics/rfm
# ──────────────────────────────────────────────────────────────────
RFM_SEGMENTS = {
    "Mistrzowie":     lambda r, f, _m: r >= 4 and f >= 4,
    "Lojalni":        lambda r, f, _m: r >= 3 and f >= 3 and not (r >= 4 and f >= 4),
    "Nowi klienci":   lambda r, f, _m: r >= 4 and f <= 2,
    "Zagrożeni":      lambda r, f, _m: r <= 2 and f >= 3,
    "Utraceni":       lambda r, f, _m: r <= 2 and f <= 2,
    "Inni":           lambda _r, _f, _m: True,
}


@router.get("/rfm")
async def rfm_analysis(
    store_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    RFM scoring with segment breakdown and CLV summary.
    """
    sql = text("""
        WITH rfm AS (
            SELECT
                customer_id,
                EXTRACT(DAY FROM NOW() - last_order_date)::int AS recency_days,
                total_orders   AS frequency,
                total_revenue  AS monetary,
                NTILE(5) OVER (ORDER BY last_order_date ASC)  AS r,
                NTILE(5) OVER (ORDER BY total_orders)         AS f,
                NTILE(5) OVER (ORDER BY total_revenue)        AS m
            FROM dim_customers
            WHERE store_id = :store_id AND total_orders > 0
        )
        SELECT customer_id, recency_days, frequency, monetary, r, f, m
        FROM rfm
    """)
    rows = (await db.execute(sql, {"store_id": store_id})).all()

    if not rows:
        return {"segments": [], "distribution": {}, "summary": {}}

    segments: dict[str, list] = defaultdict(list)
    for row in rows:
        for name, test in RFM_SEGMENTS.items():
            if test(row.r, row.f, row.m):
                segments[name].append(row)
                break

    segment_list = []
    for name, members in segments.items():
        if not members:
            continue
        segment_list.append({
            "name": name,
            "count": len(members),
            "avg_revenue": round(sum(float(m.monetary) for m in members) / len(members), 2),
            "avg_orders": round(sum(m.frequency for m in members) / len(members), 1),
            "avg_recency_days": round(sum(m.recency_days for m in members) / len(members)),
        })

    dist: dict[str, int] = defaultdict(int)
    for row in rows:
        dist[f"{row.r}{row.f}{row.m}"] += 1

    total_rev = sum(float(r.monetary) for r in rows)
    return {
        "segments": segment_list,
        "distribution": dict(dist),
        "summary": {
            "total_customers": len(rows),
            "avg_clv": round(total_rev / len(rows), 2),
            "total_revenue": round(total_rev, 2),
        },
    }


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
    since = date.today() - timedelta(days=period - 1)
    today = date.today()
    bucket_from = _date_bucket_series_sql(group_by)

    ts_sql = text(f"""
        WITH buckets AS (SELECT bucket::date AS bucket FROM {bucket_from})
        SELECT
            bu.bucket,
            agg.source_channel,
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
            GROUP BY bucket, source_channel
        ) agg ON agg.bucket = bu.bucket
        ORDER BY bu.bucket, agg.source_channel NULLS LAST
    """)
    ts_rows = (await db.execute(ts_sql, {
        "store_id": store_id, "since": since, "today": today, "trunc": group_by,
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
    summary_rows = (await db.execute(summary_sql, {
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
    since = date.today() - timedelta(days=period - 1)
    today = date.today()
    if focus_date is not None and (focus_date < since or focus_date > today):
        raise HTTPException(status_code=400, detail="focus_date outside selected period")

    has_ga4 = (await db.execute(text(
        "SELECT EXISTS (SELECT 1 FROM raw_ga4_traffic WHERE date >= :since)"
    ), {"since": since})).scalar()

    if not has_ga4:
        return {
            "has_data": False,
            "overview": None, "conversion": None, "time_series": [],
            "sources": [], "top_pages": [], "geo": [], "devices": [],
            "funnel": None,
            "focus_date": None,
        }

    if focus_date is not None:
        overview_sql = text("""
            SELECT
                COALESCE(SUM(sessions), 0)         AS sessions,
                COALESCE(SUM(total_users), 0)      AS users,
                COALESCE(SUM(new_users), 0)        AS new_users,
                ROUND(AVG(bounce_rate)::numeric, 4) AS bounce_rate,
                ROUND(AVG(avg_session_duration)::numeric, 1) AS avg_duration
            FROM raw_ga4_traffic
            WHERE date = :focus_date
        """)
        ov = (await db.execute(overview_sql, {"focus_date": focus_date})).one()
        orders_sql = text("""
            SELECT COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date = :focus_date
        """)
        ord_row = (await db.execute(orders_sql, {"store_id": store_id, "focus_date": focus_date})).one()
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
        ov = (await db.execute(overview_sql, {"since": since})).one()
        orders_sql = text("""
            SELECT COUNT(*) AS orders, COALESCE(SUM(gross_value), 0) AS revenue
            FROM fact_orders
            WHERE store_id = :store_id AND order_date::date >= :since
        """)
        ord_row = (await db.execute(orders_sql, {"store_id": store_id, "since": since})).one()

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
    ts_rows = (await db.execute(ts_sql, {
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
        src_rows = (await db.execute(sources_sql, {"focus_date": focus_date})).all()
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
        page_rows = (await db.execute(pages_sql, {"focus_date": focus_date})).all()
        geo_sql = text("""
            SELECT country, city,
                SUM(sessions) AS sessions, SUM(users) AS users
            FROM raw_ga4_geo WHERE date = :focus_date
            GROUP BY country, city
            ORDER BY sessions DESC
            LIMIT 30
        """)
        geo_rows = (await db.execute(geo_sql, {"focus_date": focus_date})).all()
        devices_sql = text("""
            SELECT device_category,
                SUM(sessions) AS sessions, SUM(users) AS users
            FROM raw_ga4_devices WHERE date = :focus_date
            GROUP BY device_category
            ORDER BY sessions DESC
        """)
        dev_rows = (await db.execute(devices_sql, {"focus_date": focus_date})).all()
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
        src_rows = (await db.execute(sources_sql, {"since": since})).all()
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
        page_rows = (await db.execute(pages_sql, {"since": since})).all()
        geo_sql = text("""
            SELECT country, city,
                SUM(sessions) AS sessions, SUM(users) AS users
            FROM raw_ga4_geo WHERE date >= :since
            GROUP BY country, city
            ORDER BY sessions DESC
            LIMIT 30
        """)
        geo_rows = (await db.execute(geo_sql, {"since": since})).all()
        devices_sql = text("""
            SELECT device_category,
                SUM(sessions) AS sessions, SUM(users) AS users
            FROM raw_ga4_devices WHERE date >= :since
            GROUP BY device_category
            ORDER BY sessions DESC
        """)
        dev_rows = (await db.execute(devices_sql, {"since": since})).all()
    dev_total = sum(r.sessions for r in dev_rows) or 1

    # Funnel data (e-commerce events from GA4)
    has_funnel = (await db.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'raw_ga4_funnel')"
    ))).scalar()

    funnel_data = None
    if has_funnel:
        if focus_date is not None:
            chk = (await db.execute(text(
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
            funnel_row = (await db.execute(funnel_sql, {"focus_date": focus_date})).one()
        else:
            chk = (await db.execute(text(
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
            funnel_row = (await db.execute(funnel_sql, {"since": since})).one()

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


# ──────────────────────────────────────────────────────────────────
# GET /analytics/cart
# ──────────────────────────────────────────────────────────────────
def _safe_table_exists_sql(table: str) -> str:
    return f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '{table}')"


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
    since = date.today() - timedelta(days=period - 1)
    today = date.today()

    has_funnel = (await db.execute(text(_safe_table_exists_sql("raw_ga4_funnel")))).scalar()
    has_devices = (await db.execute(text(_safe_table_exists_sql("raw_ga4_funnel_devices")))).scalar()
    has_products = (await db.execute(text(_safe_table_exists_sql("raw_ga4_cart_products")))).scalar()

    # ── GA4 funnel aggregates ──
    funnel = None
    if has_funnel:
        row_count = (await db.execute(text(
            "SELECT COUNT(*) FROM raw_ga4_funnel WHERE date >= :since AND (view_item > 0 OR add_to_cart > 0)"
        ), {"since": since})).scalar() or 0

        if row_count > 0:
            funnel_sql = text("""
                SELECT
                    COALESCE(SUM(view_item), 0)           AS view_item,
                    COALESCE(SUM(add_to_cart), 0)         AS add_to_cart,
                    COALESCE(SUM(begin_checkout), 0)      AS begin_checkout,
                    COALESCE(SUM(add_payment_info), 0)    AS add_payment_info,
                    COALESCE(SUM(purchase), 0)            AS purchase,
                    COALESCE(SUM(remove_from_cart), 0)    AS remove_from_cart,
                    COALESCE(SUM(add_to_cart_value), 0)   AS atc_value,
                    COALESCE(SUM(purchase_value), 0)      AS pur_value
                FROM raw_ga4_funnel WHERE date >= :since
            """)
            f = (await db.execute(funnel_sql, {"since": since})).one()
            vi, atc, bc, api_v, pur, rfc = (
                int(f.view_item), int(f.add_to_cart), int(f.begin_checkout),
                int(f.add_payment_info), int(f.purchase), int(f.remove_from_cart),
            )
            atc_val = float(f.atc_value)
            pur_val = float(f.pur_value)
            abandoned = max(atc - pur, 0)

            funnel = {
                "view_item": vi,
                "add_to_cart": atc,
                "begin_checkout": bc,
                "add_payment_info": api_v,
                "purchase": pur,
                "remove_from_cart": rfc,
                "abandoned": abandoned,
                "add_to_cart_rate": round(atc / vi * 100, 2) if vi else 0,
                "cart_abandonment_rate": round((1 - pur / atc) * 100, 2) if atc else 0,
                "checkout_abandonment_rate": round((1 - api_v / bc) * 100, 2) if bc else 0,
                "payment_to_purchase_rate": round(pur / api_v * 100, 2) if api_v else 0,
                "overall_conversion_rate": round(pur / vi * 100, 2) if vi else 0,
                "avg_cart_value": round(atc_val / atc, 2) if atc else 0,
                "avg_purchase_value": round(pur_val / pur, 2) if pur else 0,
            }

    # ── GA4 funnel daily time series ──
    funnel_ts = []
    if has_funnel:
        ts_sql = text("""
            SELECT date, view_item, add_to_cart, begin_checkout,
                   add_payment_info, purchase, remove_from_cart
            FROM raw_ga4_funnel
            WHERE date >= :since
            ORDER BY date
        """)
        for r in (await db.execute(ts_sql, {"since": since})).all():
            funnel_ts.append({
                "date": str(r.date),
                "view_item": int(r.view_item),
                "add_to_cart": int(r.add_to_cart),
                "begin_checkout": int(r.begin_checkout),
                "purchase": int(r.purchase),
                "remove_from_cart": int(r.remove_from_cart),
            })

    # ── Device segmentation ──
    device_segments = []
    if has_devices:
        dev_sql = text("""
            SELECT
                device_category,
                COALESCE(SUM(view_item), 0)        AS view_item,
                COALESCE(SUM(add_to_cart), 0)      AS add_to_cart,
                COALESCE(SUM(begin_checkout), 0)    AS begin_checkout,
                COALESCE(SUM(add_payment_info), 0)  AS add_payment_info,
                COALESCE(SUM(purchase), 0)          AS purchase,
                COALESCE(SUM(remove_from_cart), 0)  AS remove_from_cart
            FROM raw_ga4_funnel_devices
            WHERE date >= :since
            GROUP BY device_category
            ORDER BY SUM(add_to_cart) DESC
        """)
        for r in (await db.execute(dev_sql, {"since": since})).all():
            d_atc = int(r.add_to_cart)
            d_pur = int(r.purchase)
            d_vi = int(r.view_item)
            device_segments.append({
                "device": r.device_category,
                "view_item": d_vi,
                "add_to_cart": d_atc,
                "begin_checkout": int(r.begin_checkout),
                "add_payment_info": int(r.add_payment_info),
                "purchase": d_pur,
                "remove_from_cart": int(r.remove_from_cart),
                "add_to_cart_rate": round(d_atc / d_vi * 100, 2) if d_vi else 0,
                "cart_to_purchase_rate": round(d_pur / d_atc * 100, 2) if d_atc else 0,
            })

    # ── Top abandoned products ──
    top_products = []
    if has_products:
        prod_sql = text("""
            SELECT
                item_name,
                item_id,
                SUM(add_to_cart_count) AS atc,
                SUM(purchase_count)    AS purchases,
                SUM(item_revenue)      AS revenue
            FROM raw_ga4_cart_products
            WHERE date >= :since
            GROUP BY item_name, item_id
            HAVING SUM(add_to_cart_count) > 0
            ORDER BY SUM(add_to_cart_count) - SUM(purchase_count) DESC
            LIMIT 30
        """)
        for r in (await db.execute(prod_sql, {"since": since})).all():
            a = int(r.atc)
            p = int(r.purchases)
            top_products.append({
                "name": r.item_name,
                "item_id": r.item_id,
                "add_to_cart": a,
                "purchases": p,
                "drop_off": a - p,
                "drop_off_pct": round((a - p) / a * 100, 1) if a else 0,
                "revenue": round(float(r.revenue), 2),
            })

    # ── Shoper order-based metrics ──
    order_sql = text("""
        SELECT
            COUNT(*)                              AS total_orders,
            COALESCE(AVG(gross_value), 0)         AS avg_order_value,
            COALESCE(AVG(items_count), 0)         AS avg_items,
            COUNT(*) FILTER (WHERE items_count = 1) AS single_item,
            COUNT(*) FILTER (WHERE items_count > 1) AS multi_item,
            COUNT(*) FILTER (WHERE discount_value > 0) AS with_discount,
            COALESCE(AVG(gross_value) FILTER (WHERE discount_value > 0), 0) AS avg_val_discount,
            COALESCE(AVG(gross_value) FILTER (WHERE discount_value = 0), 0) AS avg_val_no_discount
        FROM fact_orders
        WHERE store_id = :store_id AND order_date::date >= :since
    """)
    o = (await db.execute(order_sql, {"store_id": store_id, "since": since})).one()

    total_orders = o.total_orders or 0
    order_metrics = {
        "total_orders": total_orders,
        "avg_order_value": round(float(o.avg_order_value), 2),
        "avg_items_per_order": round(float(o.avg_items), 1),
        "single_item_pct": round(int(o.single_item) / total_orders * 100, 1) if total_orders else 0,
        "multi_item_pct": round(int(o.multi_item) / total_orders * 100, 1) if total_orders else 0,
        "discount_pct": round(int(o.with_discount) / total_orders * 100, 1) if total_orders else 0,
        "avg_value_with_discount": round(float(o.avg_val_discount), 2),
        "avg_value_without_discount": round(float(o.avg_val_no_discount), 2),
    }

    # ── Items per order histogram ──
    hist_sql = text("""
        SELECT items_count, COUNT(*) AS order_count
        FROM fact_orders
        WHERE store_id = :store_id AND order_date::date >= :since
        GROUP BY items_count
        ORDER BY items_count
    """)
    items_histogram = [
        {"items": int(r.items_count), "orders": int(r.order_count)}
        for r in (await db.execute(hist_sql, {"store_id": store_id, "since": since})).all()
    ]

    # ── Abandoned vs purchased bar chart (daily) ──
    abandoned_vs_purchased = []
    if has_funnel:
        avp_sql = text("""
            SELECT date, add_to_cart, purchase,
                   GREATEST(add_to_cart - purchase, 0) AS abandoned
            FROM raw_ga4_funnel
            WHERE date >= :since
            ORDER BY date
        """)
        for r in (await db.execute(avp_sql, {"since": since})).all():
            abandoned_vs_purchased.append({
                "date": str(r.date),
                "purchased": int(r.purchase),
                "abandoned": int(r.abandoned),
            })

    return {
        "period_days": period,
        "has_funnel_data": funnel is not None,
        "funnel": funnel,
        "funnel_time_series": funnel_ts,
        "device_segments": device_segments,
        "top_abandoned_products": top_products,
        "order_metrics": order_metrics,
        "items_histogram": items_histogram,
        "abandoned_vs_purchased": abandoned_vs_purchased,
    }


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
