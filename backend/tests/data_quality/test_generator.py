"""Pure tests of the synthetic-data generator: no database needed."""
from datetime import date

import pytest

from app.demo.generator import DemoConfig, generate

CFG = DemoConfig(seed=3, days=40, tracker_days=7, as_of=date(2026, 6, 30))


@pytest.fixture(scope="module")
def data():
    return generate(CFG)


def test_same_seed_is_byte_identical():
    a, b = generate(CFG), generate(CFG)
    assert a["raw_orders"] == b["raw_orders"]
    assert [e["timestamp"] for e in a["tracker_events_local"]] == [e["timestamp"] for e in b["tracker_events_local"]]


def test_different_seed_differs(data):
    other = generate(DemoConfig(seed=4, days=40, tracker_days=7, as_of=CFG.as_of))
    assert other["raw_orders"] != data["raw_orders"]


def test_ids_are_unique(data):
    for table, key in (("raw_orders", "order_id"), ("raw_order_items", "order_item_id"),
                       ("raw_customers", "user_id"), ("raw_products", "product_id")):
        ids = [r[key] for r in data[table]]
        assert len(ids) == len(set(ids)), table


def test_orders_reference_known_customers_and_products(data):
    customers = {c["user_id"] for c in data["raw_customers"]}
    products = {p["product_id"] for p in data["raw_products"]}
    orders = {o["order_id"] for o in data["raw_orders"]}
    assert all(o["user_id"] is None or o["user_id"] in customers for o in data["raw_orders"])
    assert all(i["product_id"] in products and i["order_id"] in orders for i in data["raw_order_items"])


def test_order_total_is_lines_plus_shipping(data):
    lines: dict[int, float] = {}
    for i in data["raw_order_items"]:
        lines[i["order_id"]] = lines.get(i["order_id"], 0) + i["price"] * i["quantity"]
    for o in data["raw_orders"]:
        assert o["sum"] == pytest.approx(lines[o["order_id"]] + o["shipping_cost"], abs=0.011)


def test_ga4_funnel_never_grows_downstream(data):
    for f in data["raw_ga4_funnel"]:
        assert f["view_item"] >= f["add_to_cart"] >= f["begin_checkout"] >= f["add_payment_info"] >= f["purchase"]


def test_source_sessions_add_up_to_traffic(data):
    total = {t["date"]: t["sessions"] for t in data["raw_ga4_traffic"]}
    by_source: dict = {}
    for s in data["raw_ga4_sources"]:
        by_source[s["date"]] = by_source.get(s["date"], 0) + s["sessions"]
    assert by_source == total


def test_tracker_timestamps_are_epoch_milliseconds(data):
    assert all(e["timestamp"] > 1e12 for e in data["tracker_events_local"])


def test_tracker_purchases_reference_real_orders(data):
    orders = {str(o["order_id"]): float(o["sum"]) for o in data["raw_orders"]}
    purchases = [e for e in data["tracker_events_local"] if e["event_name"] == "purchase"]
    assert purchases
    for e in purchases:
        assert e["metadata"]["value"] == orders[e["metadata"]["order_id"]]
