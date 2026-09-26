"""Every check is one SQL statement.

kind="zero"       -> returns one number: violating rows. Passes when 0.
kind="reconcile"  -> returns (actual, expected). Passes when |actual-expected| / max(|expected|, 1) <= tolerance.
`requires` lists tables that must exist, otherwise the check is skipped (e.g. tracker not installed).
`:as_of` is bound to the reference date so freshness checks are reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

Kind = Literal["zero", "reconcile"]


@dataclass(frozen=True)
class Check:
    name: str
    category: str  # integrity | referential | validity | reconciliation | freshness
    description: str
    sql: str
    kind: Kind = "zero"
    tolerance: float = 0.0
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class Result:
    check: Check
    status: Literal["pass", "fail", "skip", "error"]
    actual: float | None = None
    expected: float | None = None
    detail: str = ""


TRACKER_EVENTS = (
    "'page_view','click','view_item','add_to_cart','remove_from_cart','begin_checkout','checkout_step','purchase'"
)
SOURCE_CHANNELS = "'shop','facebook','mobile','allegro','webapi','panel','admin','google','other'"

CHECKS: tuple[Check, ...] = (
    # ---- integrity -------------------------------------------------------
    Check("fact_orders_key_unique", "integrity", "one fact row per order_id",
          "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM fact_orders"),
    Check("fact_order_items_key_unique", "integrity", "one fact row per order line",
          "SELECT COUNT(*) - COUNT(DISTINCT order_item_id) FROM fact_order_items"),
    Check("fact_orders_required_columns", "integrity", "order_date, gross_value, order_status are never NULL",
          "SELECT COUNT(*) FROM fact_orders WHERE order_date IS NULL OR gross_value IS NULL OR order_status IS NULL"),
    # ---- referential -----------------------------------------------------
    Check("items_have_order", "referential", "every order line belongs to an order",
          "SELECT COUNT(*) FROM fact_order_items i LEFT JOIN fact_orders o USING (order_id) WHERE o.order_id IS NULL"),
    Check("orders_have_customer_dim", "referential", "non-guest orders point to a known customer",
          "SELECT COUNT(*) FROM fact_orders o LEFT JOIN dim_customers c ON c.customer_id = o.customer_id "
          "WHERE o.customer_id IS NOT NULL AND c.customer_id IS NULL"),
    Check("items_have_product_dim", "referential", "order lines point to a known product",
          "SELECT COUNT(*) FROM fact_order_items i LEFT JOIN dim_products p ON p.product_id = i.product_id "
          "WHERE i.product_id IS NOT NULL AND p.product_id IS NULL"),
    Check("items_have_category_dim", "referential", "order lines point to a known category",
          "SELECT COUNT(*) FROM fact_order_items i LEFT JOIN dim_categories c ON c.category_id = i.category_id "
          "WHERE i.category_id IS NOT NULL AND c.category_id IS NULL"),
    Check("products_have_category_dim", "referential", "products point to a known category",
          "SELECT COUNT(*) FROM dim_products p LEFT JOIN dim_categories c ON c.category_id = p.category_id "
          "WHERE p.category_id IS NOT NULL AND c.category_id IS NULL"),
    Check("categories_parent_exists", "referential", "category tree has no dangling parent",
          "SELECT COUNT(*) FROM dim_categories c LEFT JOIN dim_categories p ON p.category_id = c.parent_id "
          "WHERE c.parent_id IS NOT NULL AND p.category_id IS NULL"),
    # ---- validity --------------------------------------------------------
    Check("order_date_not_placeholder", "validity",
          "no 1970 placeholder dates (the transform's fallback for unparsable source dates)",
          "SELECT COUNT(*) FROM fact_orders WHERE order_date < '2000-01-01'"),
    Check("amounts_non_negative", "validity", "no negative money or non-positive quantities",
          "SELECT (SELECT COUNT(*) FROM fact_orders WHERE gross_value < 0 OR shipping_value < 0) "
          "+ (SELECT COUNT(*) FROM fact_order_items WHERE quantity <= 0)"),
    Check("source_channel_accepted", "validity", "source_channel is a mapped value",
          f"SELECT COUNT(*) FROM fact_orders WHERE source_channel NOT IN ({SOURCE_CHANNELS})"),
    Check("payment_status_accepted", "validity", "payment_status is paid|unpaid",
          "SELECT COUNT(*) FROM fact_orders WHERE payment_status NOT IN ('paid','unpaid')"),
    Check("paid_orders_have_payment_date", "validity", "paid orders carry a payment date",
          "SELECT COUNT(*) FROM fact_orders WHERE payment_status = 'paid' AND payment_date IS NULL"),
    Check("rfm_score_format", "validity", "customers with orders have a 3-digit 1-5 RFM score",
          "SELECT COUNT(*) FROM dim_customers WHERE total_orders > 0 "
          "AND (rfm_score IS NULL OR rfm_score !~ '^[1-5]{3}$')"),
    Check("ga4_funnel_is_monotonic", "validity",
          "GA4 funnel never grows step to step: view_item >= add_to_cart >= begin_checkout >= "
          "add_payment_info >= purchase",
          "SELECT COUNT(*) FROM raw_ga4_funnel WHERE NOT (view_item >= add_to_cart AND add_to_cart >= begin_checkout "
          "AND begin_checkout >= add_payment_info AND add_payment_info >= purchase)",
          requires=("raw_ga4_funnel",)),
    Check("ga4_users_not_above_sessions", "validity", "GA4 users <= sessions per day",
          "SELECT COUNT(*) FROM raw_ga4_traffic WHERE total_users > sessions", requires=("raw_ga4_traffic",)),
    Check("tracker_timestamps_are_milliseconds", "validity",
          "tracker timestamps are epoch milliseconds (tracker.js sends Date.now()), not seconds",
          "SELECT COUNT(*) FROM tracker_events_local WHERE timestamp < 100000000000",
          requires=("tracker_events_local",)),
    Check("tracker_event_names_accepted", "validity", "tracker only emits known event names",
          f"SELECT COUNT(*) FROM tracker_events_local WHERE event_name NOT IN ({TRACKER_EVENTS})",
          requires=("tracker_events_local",)),
    # ---- reconciliation --------------------------------------------------
    Check("orders_row_count_raw_vs_fact", "reconciliation", "no orders lost or duplicated by the transform",
          "SELECT (SELECT COUNT(*) FROM fact_orders), (SELECT COUNT(*) FROM raw_orders)", kind="reconcile"),
    Check("order_items_row_count_raw_vs_fact", "reconciliation", "no order lines lost by the transform",
          "SELECT (SELECT COUNT(*) FROM fact_order_items), (SELECT COUNT(*) FROM raw_order_items)",
          kind="reconcile"),
    Check("customers_row_count_raw_vs_dim", "reconciliation", "no customers lost by the transform",
          "SELECT (SELECT COUNT(*) FROM dim_customers), (SELECT COUNT(*) FROM raw_customers)", kind="reconcile"),
    Check("gross_revenue_raw_vs_fact", "reconciliation", "total revenue survives the transform",
          "SELECT (SELECT COALESCE(SUM(gross_value),0) FROM fact_orders), "
          "(SELECT COALESCE(SUM(sum),0) FROM raw_orders)",
          kind="reconcile", tolerance=0.0001),
    Check("order_total_equals_lines_plus_shipping", "reconciliation",
          "order gross = sum(line gross) + shipping (breaks when order-level discounts exist)",
          "SELECT COUNT(*) FROM fact_orders o JOIN (SELECT order_id, SUM(total_gross) g FROM fact_order_items "
          "GROUP BY order_id) i USING (order_id) WHERE ABS(o.gross_value - o.shipping_value - i.g) > 0.02"),
    Check("customer_totals_match_orders", "reconciliation",
          "dim_customers.total_orders/revenue equal the fact_orders roll-up",
          "SELECT COUNT(*) FROM dim_customers c LEFT JOIN (SELECT customer_id, COUNT(*) n, SUM(gross_value) r "
          "FROM fact_orders GROUP BY customer_id) f ON f.customer_id = c.customer_id "
          "WHERE COALESCE(f.n,0) <> c.total_orders OR ABS(COALESCE(f.r,0) - c.total_revenue) > 0.01"),
    Check("ga4_sources_vs_traffic_sessions", "reconciliation", "per-source sessions add up to total GA4 sessions",
          "SELECT (SELECT COALESCE(SUM(sessions),0) FROM raw_ga4_sources), "
          "(SELECT COALESCE(SUM(sessions),0) FROM raw_ga4_traffic)",
          kind="reconcile", tolerance=0.02, requires=("raw_ga4_sources", "raw_ga4_traffic")),
    Check("ga4_purchases_vs_orders", "reconciliation",
          "GA4 purchase events ~ real orders over the same dates (large gap = ecommerce tagging is broken)",
          "SELECT (SELECT COALESCE(SUM(purchase),0) FROM raw_ga4_funnel), "
          "(SELECT COUNT(*) FROM fact_orders WHERE order_date::date BETWEEN "
          "(SELECT MIN(date) FROM raw_ga4_funnel) AND (SELECT MAX(date) FROM raw_ga4_funnel))",
          kind="reconcile", tolerance=0.10, requires=("raw_ga4_funnel",)),
    Check("tracker_purchases_vs_orders", "reconciliation",
          "tracker purchase events ~ real orders since the tracker's first event",
          "SELECT (SELECT COUNT(*) FROM tracker_events_local WHERE event_name = 'purchase'), "
          "(SELECT COUNT(*) FROM fact_orders WHERE order_date >= date_trunc('day', "
          "to_timestamp((SELECT MIN(timestamp) FROM tracker_events_local) / 1000.0)))",
          kind="reconcile", tolerance=0.10, requires=("tracker_events_local",)),
    # ---- freshness (relative to :as_of) ----------------------------------
    Check("orders_fresh", "freshness", "newest order is at most 3 days old",
          "SELECT CASE WHEN CAST(:as_of AS date) - MAX(order_date)::date > 3 THEN 1 ELSE 0 END FROM fact_orders"),
    Check("ga4_fresh", "freshness", "newest GA4 day is at most 2 days old",
          "SELECT CASE WHEN CAST(:as_of AS date) - MAX(date) > 2 THEN 1 ELSE 0 END FROM raw_ga4_traffic",
          requires=("raw_ga4_traffic",)),
    Check("tracker_fresh", "freshness", "newest tracker event is at most 2 days old",
          "SELECT CASE WHEN CAST(:as_of AS date) - to_timestamp(MAX(timestamp) / 1000.0)::date > 2 "
          "THEN 1 ELSE 0 END FROM tracker_events_local", requires=("tracker_events_local",)),
)


async def run_checks(
    session: AsyncSession, as_of: date | None = None, checks: tuple[Check, ...] = CHECKS,
) -> list[Result]:
    as_of = as_of or date.today()
    results: list[Result] = []
    for c in checks:
        try:
            missing = [t for t in c.requires
                       if not (await session.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": t})).scalar()]
            if missing:
                results.append(Result(c, "skip", detail=f"missing table(s): {', '.join(missing)}"))
                continue
            row = (await session.execute(text(c.sql), {"as_of": as_of})).one()
            if c.kind == "zero":
                n = float(row[0] or 0)
                results.append(Result(c, "pass" if n == 0 else "fail", actual=n, expected=0,
                                      detail="" if n == 0 else f"{n:g} violating row(s)"))
            else:
                actual, expected = float(row[0] or 0), float(row[1] or 0)
                rel = abs(actual - expected) / max(abs(expected), 1.0)
                ok = rel <= c.tolerance
                detail = "" if ok else f"{actual:g} vs {expected:g} ({rel:.1%} off, tolerance {c.tolerance:.1%})"
                results.append(Result(c, "pass" if ok else "fail", actual, expected, detail))
        except Exception as exc:  # a broken check must not hide the others
            await session.rollback()
            results.append(Result(c, "error", detail=f"{type(exc).__name__}: {str(exc).splitlines()[0]}"))
    return results
