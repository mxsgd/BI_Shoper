"""RAW -> CORE pipeline quality, run against the seeded synthetic store."""
import pytest
from sqlalchemy import text

from app.quality import CHECKS, run_checks
from app.services.analytics_core.tracker import TrackerService
from app.services.transform_service import TransformService

from .conftest import CONFIG


async def _count(session, table: str) -> int:
    return (await session.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar()


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.name)
async def test_quality_check(session, check):
    (result,) = await run_checks(session, CONFIG.as_of, (check,))
    assert result.status in ("pass", "skip"), f"{check.name}: {result.detail}"


async def test_transform_is_idempotent(session):
    tables = ("fact_orders", "fact_order_items", "dim_customers", "dim_products", "dim_categories")
    before = {t: await _count(session, t) for t in tables}
    revenue = (await session.execute(text("SELECT SUM(gross_value) FROM fact_orders"))).scalar()

    await TransformService(session).run_all()
    await TransformService(session).run_all()

    assert {t: await _count(session, t) for t in tables} == before
    assert (await session.execute(text("SELECT SUM(gross_value) FROM fact_orders"))).scalar() == revenue


async def test_transform_drops_fact_lines_whose_raw_line_was_replaced(session):
    """Regression: RAW lines are replaced on re-sync; stale fact lines used to survive and double-count."""
    victim = (await session.execute(text("SELECT order_item_id FROM raw_order_items ORDER BY 1 LIMIT 1"))).scalar()
    saved = (await session.execute(
        text("SELECT * FROM raw_order_items WHERE order_item_id = :i"), {"i": victim})).mappings().one()
    try:
        await session.execute(text("DELETE FROM raw_order_items WHERE order_item_id = :i"), {"i": victim})
        await session.commit()
        await TransformService(session).transform_fact_order_items()
        assert (await session.execute(
            text("SELECT COUNT(*) FROM fact_order_items WHERE order_item_id = :i"), {"i": victim})).scalar() == 0
    finally:
        cols = ", ".join(k for k in saved if k != "id")
        await session.execute(
            text(f"INSERT INTO raw_order_items ({cols}) VALUES ({', '.join(':' + k for k in saved if k != 'id')})"),
            {k: v for k, v in saved.items() if k != "id"})
        await session.commit()
        await TransformService(session).transform_fact_order_items()


async def test_tracker_period_filter_uses_milliseconds(session):
    """Regression: timestamps are epoch ms but the cutoff was epoch seconds, so every period matched all rows."""
    svc = TrackerService(session)
    week = await svc.tracker_events_summary(1, 7)
    everything = await svc.tracker_events_summary(1, 365)
    # The seeded tracker covers the last 14 days, so a 7-day window holds about half of it while 365 days holds
    # all of it - a seconds-vs-ms mixup would make both equal.
    assert everything["total_events"] > 0
    assert week["total_events"] < everything["total_events"]
