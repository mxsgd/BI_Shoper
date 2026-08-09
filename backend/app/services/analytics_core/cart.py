from datetime import date, timedelta, datetime


from typing_extensions import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

def _safe_table_exists_sql(table: str) -> str:
    return f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '{table}')"

class CartService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_cart(
            self,
            store_id: int,
            period: int) -> dict:

        since = date.today() - timedelta(days=period - 1)
        today = date.today()
    
        has_funnel = (await self.db.execute(text(_safe_table_exists_sql("raw_ga4_funnel")))).scalar()
        has_devices = (await self.db.execute(text(_safe_table_exists_sql("raw_ga4_funnel_devices")))).scalar()
        has_products = (await self.db.execute(text(_safe_table_exists_sql("raw_ga4_cart_products")))).scalar()
        has_tracker = (await self.db.execute(text(_safe_table_exists_sql("tracker_events_local")))).scalar()
    
        tracker_funnel = None
        tracker_funnel_ts = []
        tracker_top_products = []
        tracker_abandoned_vs_purchased = []
    
        # ── Tracker-based funnel (preferred over GA4 when available) ──
        if has_tracker:
            now = datetime.utcnow()
            since_epoch = int((now - timedelta(days=period)).timestamp())
            tracker_count = (await self.db.execute(text("""
                SELECT COUNT(*)
                FROM tracker_events_local
                WHERE timestamp >= :since_epoch
                AND event_name IN ('view_item', 'add_to_cart', 'begin_checkout', 'checkout_step', 'purchase', 'remove_from_cart')
            """), {"since_epoch": since_epoch})).scalar() or 0
    
            if tracker_count > 0:
                tracker_funnel_sql = text("""
                    SELECT
                        COUNT(*) FILTER (WHERE event_name = 'view_item') AS view_item,
                        COUNT(*) FILTER (WHERE event_name = 'add_to_cart') AS add_to_cart,
                        COUNT(*) FILTER (WHERE event_name = 'begin_checkout') AS begin_checkout,
                        COUNT(*) FILTER (
                            WHERE event_name = 'checkout_step'
                            AND COALESCE(metadata->>'step', '') = 'payment'
                        ) AS add_payment_info,
                        COUNT(*) FILTER (WHERE event_name = 'purchase') AS purchase,
                        COUNT(*) FILTER (WHERE event_name = 'remove_from_cart') AS remove_from_cart,
                        AVG(
                            CASE
                                WHEN event_name = 'add_to_cart'
                                AND COALESCE(metadata->>'price', '') ~ '^-?\\d+(\\.\\d+)?$'
                                THEN (metadata->>'price')::numeric
                            END
                        ) AS avg_cart_value,
                        AVG(
                            CASE
                                WHEN event_name = 'purchase'
                                AND COALESCE(metadata->>'value', '') ~ '^-?\\d+(\\.\\d+)?$'
                                THEN (metadata->>'value')::numeric
                            END
                        ) AS avg_purchase_value
                    FROM tracker_events_local
                    WHERE timestamp >= :since_epoch
                """)
                tf = (await self.db.execute(tracker_funnel_sql, {"since_epoch": since_epoch})).one()
                vi = int(tf.view_item or 0)
                atc = int(tf.add_to_cart or 0)
                bc = int(tf.begin_checkout or 0)
                api_v = int(tf.add_payment_info or 0)
                pur = int(tf.purchase or 0)
                rfc = int(tf.remove_from_cart or 0)
                abandoned = max(atc - pur, 0)
                avg_cart_value = float(tf.avg_cart_value or 0)
                avg_purchase_value = float(tf.avg_purchase_value or 0)
    
                tracker_funnel = {
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
                    "avg_cart_value": round(avg_cart_value, 2),
                    "avg_purchase_value": round(avg_purchase_value, 2),
                }
    
                tracker_ts_sql = text("""
                    SELECT
                        d.day::date AS date,
                        COALESCE(agg.view_item, 0) AS view_item,
                        COALESCE(agg.add_to_cart, 0) AS add_to_cart,
                        COALESCE(agg.begin_checkout, 0) AS begin_checkout,
                        COALESCE(agg.purchase, 0) AS purchase,
                        COALESCE(agg.remove_from_cart, 0) AS remove_from_cart
                    FROM generate_series(CAST(:since AS date), CAST(:today AS date), interval '1 day') AS d(day)
                    LEFT JOIN (
                        SELECT
                            to_timestamp(timestamp)::date AS dt,
                            COUNT(*) FILTER (WHERE event_name = 'view_item') AS view_item,
                            COUNT(*) FILTER (WHERE event_name = 'add_to_cart') AS add_to_cart,
                            COUNT(*) FILTER (WHERE event_name = 'begin_checkout') AS begin_checkout,
                            COUNT(*) FILTER (WHERE event_name = 'purchase') AS purchase,
                            COUNT(*) FILTER (WHERE event_name = 'remove_from_cart') AS remove_from_cart
                        FROM tracker_events_local
                        WHERE timestamp >= :since_epoch
                        GROUP BY dt
                    ) agg ON agg.dt = d.day::date
                    ORDER BY d.day
                """)
                for r in (await self.db.execute(tracker_ts_sql, {
                    "since": since,
                    "today": today,
                    "since_epoch": since_epoch,
                })).all():
                    tracker_funnel_ts.append({
                        "date": str(r.date),
                        "view_item": int(r.view_item),
                        "add_to_cart": int(r.add_to_cart),
                        "begin_checkout": int(r.begin_checkout),
                        "purchase": int(r.purchase),
                        "remove_from_cart": int(r.remove_from_cart),
                    })
                    tracker_abandoned_vs_purchased.append({
                        "date": str(r.date),
                        "purchased": int(r.purchase),
                        "abandoned": max(int(r.add_to_cart) - int(r.purchase), 0),
                    })
    
                tracker_products_sql = text("""
                    WITH atc AS (
                        SELECT
                            COALESCE(NULLIF(metadata->>'product_name', ''), 'Unknown product') AS name,
                            NULLIF(metadata->>'product_id', '') AS item_id,
                            COUNT(*) AS add_to_cart,
                            AVG(
                                CASE
                                    WHEN COALESCE(metadata->>'price', '') ~ '^-?\\d+(\\.\\d+)?$'
                                    THEN (metadata->>'price')::numeric
                                END
                            ) AS avg_price
                        FROM tracker_events_local
                        WHERE timestamp >= :since_epoch
                        AND event_name = 'add_to_cart'
                        GROUP BY name, item_id
                    )
                    SELECT
                        name,
                        item_id,
                        add_to_cart,
                        0::bigint AS purchases,
                        add_to_cart::bigint AS drop_off,
                        100::numeric AS drop_off_pct,
                        ROUND(COALESCE(add_to_cart * avg_price, 0), 2) AS revenue
                    FROM atc
                    ORDER BY add_to_cart DESC
                    LIMIT 30
                """)
                for r in (await self.db.execute(tracker_products_sql, {"since_epoch": since_epoch})).all():
                    tracker_top_products.append({
                        "name": r.name,
                        "item_id": r.item_id,
                        "add_to_cart": int(r.add_to_cart),
                        "purchases": int(r.purchases),
                        "drop_off": int(r.drop_off),
                        "drop_off_pct": float(r.drop_off_pct),
                        "revenue": round(float(r.revenue or 0), 2),
                    })
                    
            # ── GA4 funnel aggregates ──
            funnel = None
            if has_funnel:
                row_count = (await self.db.execute(text(
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
                    f = (await self.db.execute(funnel_sql, {"since": since})).one()
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
                for r in (await self.db.execute(ts_sql, {"since": since})).all():
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
                for r in (await self.db.execute(dev_sql, {"since": since})).all():
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
                for r in (await self.db.execute(prod_sql, {"since": since})).all():
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
            o = (await self.db.execute(order_sql, {"store_id": store_id, "since": since})).one()

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
                for r in (await self.db.execute(hist_sql, {"store_id": store_id, "since": since})).all()
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
                for r in (await self.db.execute(avp_sql, {"since": since})).all():
                    abandoned_vs_purchased.append({
                        "date": str(r.date),
                        "purchased": int(r.purchase),
                        "abandoned": int(r.abandoned),
                    })

            return {
                "period_days": period,
                # Twardy podział źródeł: /cart = tracker.
                "has_funnel_data": tracker_funnel is not None,
                "funnel": tracker_funnel,
                "funnel_time_series": tracker_funnel_ts,
                "device_segments": [],
                "top_abandoned_products": tracker_top_products,
                "order_metrics": order_metrics,
                "items_histogram": items_histogram,
                "abandoned_vs_purchased": tracker_abandoned_vs_purchased,
            }