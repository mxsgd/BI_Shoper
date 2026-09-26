"""Deterministic synthetic store: RAW-layer rows only, no database access.

The same (seed, as_of, days) always yields byte-identical data, so tests and
screenshots are reproducible. Everything is derived from one causal chain:

    sessions/day -> orders/day -> order lines -> GA4 funnel + tracker events

so cross-source reconciliation (GA4 vs orders vs tracker) holds by construction,
like it would for a store whose tracking is correctly instrumented.
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

STORE_ID = 1
SITE = "https://demo-store.example.com"
CURRENCY = "PLN"

# (category_id, name, parent_id)
CATEGORIES = [
    (1, "Mattresses", None), (2, "Beds", None), (3, "Bedding", None), (4, "Furniture", None),
    (11, "Foam mattresses", 1), (12, "Pocket spring mattresses", 1), (13, "Mattress toppers", 1),
    (21, "Upholstered beds", 2), (22, "Wooden beds", 2),
    (31, "Pillows", 3), (32, "Duvets", 3), (33, "Mattress protectors", 3),
    (41, "Sofas", 4), (42, "Armchairs", 4),
]
# leaf category -> (price_low, price_high)
LEAF_PRICES = {
    11: (390, 1290), 12: (890, 2490), 13: (149, 449),
    21: (1190, 3290), 22: (990, 2790),
    31: (49, 189), 32: (129, 449), 33: (59, 219),
    41: (1690, 4990), 42: (690, 2190),
}
PRODUCERS = [(1, "Nordic Sleep"), (2, "Comfort Line"), (3, "Ortho Works")]
STATUSES = {1: "New", 2: "Processing", 3: "Shipped", 4: "Completed", 5: "Cancelled"}
ADJECTIVES = ["Comfort", "Premium", "Classic", "Eco", "Ortho"]
SINGULAR = {
    11: "Foam Mattress", 12: "Pocket Mattress", 13: "Topper", 21: "Upholstered Bed",
    22: "Wooden Bed", 31: "Pillow", 32: "Duvet", 33: "Mattress Protector",
    41: "Sofa", 42: "Armchair",
}

SOURCES = [  # (source, medium, share, conversion propensity)
    ("google", "organic", 0.38, 1.0), ("(direct)", "(none)", 0.27, 1.1),
    ("google", "cpc", 0.12, 1.3), ("facebook", "referral", 0.08, 0.6),
    ("newsletter", "email", 0.06, 1.8), ("allegro.pl", "referral", 0.05, 0.8),
    ("bing", "organic", 0.04, 0.9),
]
CITIES = [("Warsaw", 0.24), ("Krakow", 0.14), ("Wroclaw", 0.12), ("Poznan", 0.11),
          ("Gdansk", 0.10), ("Lodz", 0.09), ("Katowice", 0.11), ("Szczecin", 0.09)]
DEVICES = [("desktop", "Chrome", "Windows", 0.30), ("mobile", "Safari", "iOS", 0.26),
           ("mobile", "Chrome", "Android", 0.24), ("desktop", "Edge", "Windows", 0.14),
           ("tablet", "Safari", "iOS", 0.06)]
DEVICE_SHARE = {"desktop": 0.44, "mobile": 0.50, "tablet": 0.06}
PAGES = [("/", "Home", 0.22), ("/pl/c/foam-mattresses/11", "Foam mattresses", 0.13),
         ("/pl/c/pocket-mattresses/12", "Pocket spring mattresses", 0.10),
         ("/pl/c/beds/2", "Beds", 0.09), ("/pl/c/bedding/3", "Bedding", 0.07),
         ("/pl/basket", "Basket", 0.06), ("/pl/i/contact/9", "Contact", 0.04),
         ("/pl/i/delivery/12", "Delivery", 0.05), ("/pl/c/sofas/41", "Sofas", 0.08),
         ("/pl/c/sale/92", "Sale", 0.16)]
WEEKDAY = [1.05, 1.05, 1.0, 1.0, 0.95, 0.85, 0.90]  # Mon..Sun
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 8, 8, 8, 8, 8, 9, 10, 11, 12, 12, 10, 6, 3]
FIRST = ["Anna", "Piotr", "Katarzyna", "Marek", "Ewa", "Tomasz", "Agnieszka", "Jan", "Maria", "Pawel"]
LAST = ["Nowak", "Kowalski", "Wisniewski", "Wojcik", "Kaminski", "Lewandowski", "Zielinski", "Szymanski"]


@dataclass(frozen=True)
class DemoConfig:
    seed: int = 42
    days: int = 180              # order / GA4 history length
    tracker_days: int = 30       # tracker was "installed" this many days ago
    as_of: date = field(default_factory=date.today)
    base_sessions: int = 380     # GA4 sessions per day before trend/season factors
    conversion_rate: float = 0.022


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 40:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _split(total: int, weights: list[float]) -> list[int]:
    """Split an integer into parts proportional to weights; parts sum to total exactly."""
    s = sum(weights)
    raw = [total * w / s for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True)[: total - sum(out)]:
        out[i] += 1
    return out


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _pick_time(rng: random.Random, day: date) -> datetime:
    hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
    return datetime(day.year, day.month, day.day, hour, rng.randrange(60), rng.randrange(60))


def generate(config: DemoConfig | None = None) -> dict[str, list[dict]]:
    """Return {table_name: [row, ...]} in dependency order."""
    cfg = config or DemoConfig()
    rng = random.Random(cfg.seed)
    t: dict[str, list[dict]] = {}

    t["stores"] = [{"id": STORE_ID, "name": "Demo Store", "api_url": SITE, "api_token": "", "is_active": True}]
    t["raw_taxes"] = [{"store_id": STORE_ID, "tax_id": 1, "value": 23, "name": "VAT 23%"}]
    t["raw_statuses"] = [{"store_id": STORE_ID, "status_id": k, "name": v} for k, v in STATUSES.items()]
    t["raw_producers"] = [{"store_id": STORE_ID, "producer_id": i, "name": n} for i, n in PRODUCERS]
    t["raw_categories"] = [
        {"store_id": STORE_ID, "category_id": cid, "root": parent is None, "order": cid,
         "translations": {"pl_PL": {"name": name}, "_parent_id": parent}}
        for cid, name, parent in CATEGORIES
    ]

    # ---- products -------------------------------------------------------
    products: list[dict] = []
    for leaf, (lo, hi) in LEAF_PRICES.items():
        for n in range(rng.randint(4, 6)):
            pid = 1000 + len(products)
            price = round(rng.uniform(lo, hi) / 10) * 10 - 0.01
            products.append({
                "id": pid, "leaf": leaf, "price": price, "cost": round(price * rng.uniform(0.52, 0.7), 2),
                "producer": rng.choice(PRODUCERS)[0], "code": f"SKU-{pid}",
                "name": f"{rng.choice(ADJECTIVES)} {SINGULAR[leaf]} {n + 1}",
            })
    rng.shuffle(products)
    pop_weights = [1 / (rank + 1) ** 0.9 for rank in range(len(products))]
    start = cfg.as_of - timedelta(days=cfg.days)
    t["raw_products"] = [
        {"store_id": STORE_ID, "product_id": p["id"], "type": 0, "producer_id": p["producer"],
         "category_id": p["leaf"], "tax_id": 1, "code": p["code"], "currency_id": 1,
         "add_date": _ts(datetime.combine(start - timedelta(days=90), datetime.min.time())),
         "stock": {"price": p["price"]},
         "translations": {"pl_PL": {"name": p["name"], "active": 1}}}
        for p in products
    ]
    t["raw_product_stocks"] = [
        {"store_id": STORE_ID, "stock_id": 90000 + p["id"], "product_id": p["id"], "extended": False,
         "active": True, "default": True, "code": p["code"], "price": p["price"],
         "price_buying": p["cost"], "stock": rng.randint(5, 80)}
        for p in products
    ]

    # ---- sessions -> orders -> lines -----------------------------------
    customers: list[dict] = []
    cust_orders: dict[int, int] = {}
    orders: list[dict] = []
    items: list[dict] = []
    per_day: list[dict] = []
    order_id, item_id = 100000, 500000
    end_of_data = datetime.combine(cfg.as_of, datetime.max.time()).replace(microsecond=0)

    for i in range(cfg.days + 1):
        day = start + timedelta(days=i)
        season = 1 + 0.15 * math.sin(2 * math.pi * day.timetuple().tm_yday / 365)
        trend = 0.75 + 0.5 * i / cfg.days
        sessions = max(20, round(cfg.base_sessions * trend * season * WEEKDAY[day.weekday()] * rng.uniform(0.88, 1.12)))
        n_orders = _poisson(rng, sessions * cfg.conversion_rate * rng.uniform(0.85, 1.15))
        times = sorted(_pick_time(rng, day) for _ in range(n_orders))
        day_lines: list[dict] = []
        day_revenue, day_order_ids = 0.0, []

        for when in times:
            order_id += 1
            if rng.random() < 0.08:
                user_id = None
                cust = None
            elif customers and rng.random() < 0.38:
                cust = rng.choices(customers, weights=[1 + cust_orders[c["user_id"]] for c in customers])[0]
                user_id = cust["user_id"]
            else:
                user_id = 5000 + len(customers)
                first, last = rng.choice(FIRST), rng.choice(LAST)
                cust = {"store_id": STORE_ID, "user_id": user_id, "email": f"{first}.{last}{user_id}@example.com".lower(),
                        "firstname": first, "lastname": last, "date_add": _ts(when), "lastvisit": _ts(when),
                        "discount": 0, "active": True, "group_id": 1, "origin": 0}
                customers.append(cust)
                cust_orders[user_id] = 0
            if user_id is not None:
                cust_orders[user_id] += 1
                cust["lastvisit"] = _ts(when)

            n_lines = rng.choices([1, 2, 3, 4], weights=[62, 26, 9, 3])[0]
            chosen: list[dict] = []
            while len(chosen) < n_lines:
                p = rng.choices(products, weights=pop_weights)[0]
                if p not in chosen:
                    chosen.append(p)
            goods = 0.0
            order_lines = []
            for p in chosen:
                qty = rng.choices([1, 2, 3], weights=[85, 11, 4])[0]
                item_id += 1
                order_lines.append({"store_id": STORE_ID, "order_id": order_id, "order_item_id": item_id,
                                    "product_id": p["id"], "stock_id": 90000 + p["id"], "price": p["price"],
                                    "discount_perc": 0, "quantity": qty, "name": p["name"], "code": p["code"],
                                    "tax": "23%", "tax_value": 23, "unit": "pcs"})
                goods += p["price"] * qty
            shipping = 0.0 if goods >= 500 else 19.99
            total = round(goods + shipping, 2)

            age = (cfg.as_of - day).days
            if age > 14:
                status = rng.choices([4, 5, 3], weights=[90, 6, 4])[0]
            elif age > 3:
                status = rng.choices([3, 4, 2, 5], weights=[50, 35, 10, 5])[0]
            else:
                status = rng.choices([1, 2, 3, 5], weights=[40, 35, 20, 5])[0]
            paid = status in (2, 3, 4) or (status == 1 and rng.random() < 0.25)
            status_dt = min(when + timedelta(hours=rng.randint(1, 48)), end_of_data) if status != 1 else when
            orders.append({
                "store_id": STORE_ID, "order_id": order_id, "user_id": user_id, "date": _ts(when),
                "status_date": _ts(status_dt), "status_id": status, "sum": total,
                "payment_id": rng.randint(1, 3), "shipping_id": rng.randint(1, 2), "shipping_cost": shipping,
                "email": cust["email"] if cust else f"guest{order_id}@example.com",
                "code": f"ORD-{day.year}-{order_id}", "confirm": True, "currency_id": 1, "currency_rate": 1,
                "paid": total if paid else 0, "discount_client": 0, "discount_group": 0, "discount_levels": 0,
                "discount_code": 0, "promo_code": None, "is_paid": paid,
                "total_products": sum(int(l["quantity"]) for l in order_lines),
                "origin": rng.choices([0, 3, 2, 1], weights=[78, 12, 6, 4])[0],
            })
            items.extend(order_lines)
            day_lines.extend(order_lines)
            day_revenue += total
            day_order_ids.append(order_id)

        per_day.append({"day": day, "sessions": sessions, "orders": n_orders,
                        "revenue": round(day_revenue, 2), "order_ids": day_order_ids, "lines": day_lines})

    t["raw_customers"] = customers
    t["raw_orders"] = orders
    t["raw_order_items"] = items

    _ga4(t, per_day, products, rng)
    _tracker(t, per_day, orders, products, cfg, rng)
    return t


def _ga4(t: dict, per_day: list[dict], products: list[dict], rng: random.Random) -> None:
    by_id = {p["id"]: p for p in products}
    for k in ("raw_ga4_traffic", "raw_ga4_sources", "raw_ga4_pages", "raw_ga4_geo", "raw_ga4_devices",
              "raw_ga4_funnel", "raw_ga4_funnel_devices", "raw_ga4_cart_products"):
        t[k] = []
    for d in per_day:
        day, s, n_orders = d["day"], d["sessions"], d["orders"]
        users = round(s * 0.86)
        page_views = round(s * rng.uniform(3.6, 4.6))
        bounce = round(rng.uniform(0.27, 0.36), 4)
        d["ga4"] = {"users": users, "page_views": page_views}
        t["raw_ga4_traffic"].append({
            "date": day, "sessions": s, "total_users": users, "new_users": round(users * 0.62),
            "page_views": page_views, "bounce_rate": bounce, "avg_session_duration": round(rng.uniform(150, 240), 2),
            "engaged_sessions": round(s * (1 - bounce)), "events_count": round(page_views * 3.4)})

        conv = _split(n_orders, [w * m for _, _, w, m in SOURCES])
        for (src, med, _, _), ss, cv in zip(SOURCES, _split(s, [w for *_, w, _ in SOURCES]), conv):
            t["raw_ga4_sources"].append({
                "date": day, "source": src, "medium": med, "campaign": None, "sessions": ss,
                "users": round(ss * 0.86), "new_users": round(ss * 0.5), "engaged_sessions": round(ss * 0.68),
                "conversions": cv, "revenue": round(d["revenue"] * cv / n_orders, 2) if n_orders else 0})

        for (path, title, _), pv, ent, ex in zip(
            PAGES, _split(page_views, [w * rng.uniform(0.9, 1.1) for *_, w in PAGES]),
            _split(s, [w for *_, w in PAGES]), _split(round(s * 0.9), [w for *_, w in PAGES]),
        ):
            t["raw_ga4_pages"].append({"date": day, "page_path": path, "page_title": title, "page_views": pv,
                                       "avg_time_on_page": round(rng.uniform(35, 120), 2), "entrances": ent,
                                       "exits": ex, "bounce_rate": round(rng.uniform(0.2, 0.5), 4)})
        for (city, _), ss in zip(CITIES, _split(s, [w for _, w in CITIES])):
            t["raw_ga4_geo"].append({"date": day, "country": "Poland", "city": city, "sessions": ss,
                                     "users": round(ss * 0.86), "new_users": round(ss * 0.55)})
        for (dev, browser, os_, _), ss in zip(DEVICES, _split(s, [w for *_, w in DEVICES])):
            t["raw_ga4_devices"].append({"date": day, "device_category": dev, "browser": browser, "os": os_,
                                         "sessions": ss, "users": round(ss * 0.86)})

        purchase = round(n_orders * rng.uniform(0.92, 1.0))
        pay = math.ceil(purchase / 0.85)
        begin = math.ceil(pay / 0.7)
        cart = math.ceil(begin / 0.45)
        view = min(math.ceil(cart / 0.09), page_views)
        d["funnel"] = {"view_item": view, "add_to_cart": cart, "begin_checkout": begin,
                       "add_payment_info": pay, "purchase": purchase, "remove_from_cart": round(cart * 0.2)}
        avg_price = sum(l["price"] for l in d["lines"]) / len(d["lines"]) if d["lines"] else 0
        t["raw_ga4_funnel"].append({
            "date": day, **d["funnel"], "add_to_cart_value": round(cart * avg_price, 2),
            "purchase_value": round(d["revenue"] * purchase / n_orders, 2) if n_orders else 0})
        shares = list(DEVICE_SHARE.items())
        cols = {k: _split(v, [sh for _, sh in shares]) for k, v in d["funnel"].items()}
        for j, (dev, _) in enumerate(shares):
            t["raw_ga4_funnel_devices"].append({"date": day, "device_category": dev,
                                                **{k: cols[k][j] for k in d["funnel"]}})

        sold: dict[int, list[float]] = {}
        for l in d["lines"]:
            agg = sold.setdefault(l["product_id"], [0, 0.0])
            agg[0] += int(l["quantity"])
            agg[1] += float(l["price"]) * float(l["quantity"])
        for pid, (qty, rev) in sold.items():
            t["raw_ga4_cart_products"].append({
                "date": day, "item_name": by_id[pid]["name"], "item_id": by_id[pid]["code"],
                "add_to_cart_count": qty * rng.randint(3, 6), "purchase_count": qty, "item_revenue": round(rev, 2)})


def _tracker(t: dict, per_day: list[dict], orders: list[dict], products: list[dict],
             cfg: DemoConfig, rng: random.Random) -> None:
    """Events for the last tracker_days. timestamp is epoch *milliseconds* (tracker.js: Date.now())."""
    rows: list[dict] = []
    order_by_id = {o["order_id"]: o for o in orders}
    synced = datetime.combine(cfg.as_of, datetime.max.time())

    def event(day: date, name: str, user: dict, path: str, meta: dict) -> None:
        when = _pick_time(rng, day)
        rows.append({
            "id": uuid.UUID(int=rng.getrandbits(128), version=4), "api_key": "demo-key", "event_name": name,
            "user_id": user["id"], "url": SITE + path,
            "timestamp": int(when.replace(tzinfo=timezone.utc).timestamp() * 1000),
            "metadata": {"device_category": user["device"], "session_id": user["sid"], **meta},
            "synced_at": synced})

    for d in per_day[-cfg.tracker_days:]:
        day, f = d["day"], d["funnel"]
        pool = [{"id": f"u_{rng.getrandbits(48):012x}", "sid": f"s_{rng.getrandbits(48):012x}",
                 "device": rng.choices(list(DEVICE_SHARE), weights=list(DEVICE_SHARE.values()))[0]}
                for _ in range(max(1, d["ga4"]["users"]))]
        pick = lambda: rng.choice(pool)  # noqa: E731
        for _ in range(d["ga4"]["page_views"]):
            path, title, _ = rng.choices(PAGES, weights=[w for *_, w in PAGES])[0]
            event(day, "page_view", pick(), path, {"referrer": "", "title": title})
        for _ in range(round(d["ga4"]["page_views"] * 0.45)):
            event(day, "click", pick(), rng.choice(PAGES)[0], {"tag": "A", "text": "read more"})
        for name in ("view_item", "add_to_cart"):
            for _ in range(f[name]):
                p = rng.choices(products, weights=[1 / (r + 1) ** 0.9 for r in range(len(products))])[0]
                event(day, name, pick(), f"/pl/p/{p['code'].lower()}/{p['id']}",
                      {"product_id": str(p["id"]), "product_name": p["name"], "price": p["price"],
                       "currency": CURRENCY})
        for _ in range(f["remove_from_cart"]):
            event(day, "remove_from_cart", pick(), "/pl/basket", {"tag": "BUTTON", "text": "remove"})
        for _ in range(f["begin_checkout"]):
            event(day, "begin_checkout", pick(), "/pl/basket", {"step": "entry", "path": "/pl/basket"})
        for step, share in (("address", 1.0), ("shipping", 0.85), ("payment", 0.75), ("review", 0.7)):
            for _ in range(round(f["begin_checkout"] * share)):
                event(day, "checkout_step", pick(), f"/pl/order/{step}", {"step": step, "source": "page"})
        for oid in d["order_ids"][: f["purchase"]]:
            o = order_by_id[oid]
            event(day, "purchase", pick(), "/pl/order/thank-you",
                  {"order_id": str(oid), "value": float(o["sum"]), "currency": CURRENCY, "items": []})
    t["tracker_events_local"] = rows
