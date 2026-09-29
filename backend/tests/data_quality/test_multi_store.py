"""Two shops share Shoper ids (every shop has an order #1); neither may overwrite the other.

Seeds its own database, then copies the whole RAW layer of store 1 into a second store with the
exact same Shoper ids - the worst case - and runs the transform. Before CORE was keyed by
(store_id, id), store 2's rows replaced store 1's.
"""
import asyncio
import os

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.config import get_settings
from app.database import Base
from app.demo.generator import DemoConfig
from app.demo.seed import demo_url_from, seed_database
from app.services.transform_service import TransformService

from .conftest import CONFIG

CORE_TABLES = ("fact_orders", "fact_order_items", "dim_products", "dim_customers", "dim_categories")


@pytest.fixture(scope="module")
def two_store_db_url() -> str:
    source = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    url = demo_url_from(source, "_tenancy_test")
    try:
        asyncio.run(seed_database(url, DemoConfig(seed=CONFIG.seed, days=30, tracker_days=0, as_of=CONFIG.as_of)))
    except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as exc:
        if os.environ.get("REQUIRE_POSTGRES"):
            raise
        pytest.skip(f"Postgres not available: {exc}")
    return url


async def _per_store(session, table: str) -> dict[int, int]:
    rows = await session.execute(text(f"SELECT store_id, COUNT(*) FROM {table} GROUP BY store_id"))
    return dict(rows.all())


async def _clone_store(session, source_id: int) -> int:
    # Explicit id: the seeder inserts stores with fixed ids, so the id sequence is still at 1.
    store_cols = [c.name for c in Base.metadata.tables["stores"].columns if c.name != "id"]
    new_id = (await session.execute(text(
        f"INSERT INTO stores (id, {', '.join(store_cols)}) "
        f"SELECT (SELECT MAX(id) + 1 FROM stores), {', '.join(store_cols)} FROM stores "
        "WHERE id = :s RETURNING id"), {"s": source_id})).scalar()
    for name, table in Base.metadata.tables.items():
        if not name.startswith("raw_") or "store_id" not in table.columns:
            continue
        cols = [f'"{c.name}"' for c in table.columns if c.name != "id"]  # quoted: raw_payments has "order"
        select = ", ".join(":new" if c == '"store_id"' else c for c in cols)
        await session.execute(
            text(f"INSERT INTO {name} ({', '.join(cols)}) SELECT {select} FROM {name} WHERE store_id = :s"),
            {"s": source_id, "new": new_id})
    await session.commit()
    return new_id


async def test_second_store_with_same_ids_does_not_overwrite_first(two_store_db_url):
    engine = create_async_engine(two_store_db_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            (store_1,) = (await session.execute(text("SELECT id FROM stores"))).scalars().all()
            before = {t: await _per_store(session, t) for t in CORE_TABLES}
            revenue_before = (await session.execute(text(
                "SELECT SUM(gross_value) FROM fact_orders WHERE store_id = :s"), {"s": store_1})).scalar()
            rfm_before = dict((await session.execute(text(
                "SELECT customer_id, rfm_score FROM dim_customers WHERE store_id = :s"), {"s": store_1})).all())

            store_2 = await _clone_store(session, store_1)
            await TransformService(session).run_all()

            for table in CORE_TABLES:
                counts = await _per_store(session, table)
                assert counts[store_1] == before[table][store_1] > 0, f"{table}: store 1 lost rows"
                assert counts[store_2] == counts[store_1], f"{table}: store 2 incomplete"

            revenue = dict((await session.execute(text(
                "SELECT store_id, SUM(gross_value) FROM fact_orders GROUP BY store_id"))).all())
            assert revenue == {store_1: revenue_before, store_2: revenue_before}

            # RFM quintiles rank a customer within their own shop, so adding a shop changes nothing.
            rfm_after = dict((await session.execute(text(
                "SELECT customer_id, rfm_score FROM dim_customers WHERE store_id = :s"), {"s": store_1})).all())
            assert rfm_after == rfm_before
    finally:
        await engine.dispose()
