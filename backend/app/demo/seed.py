"""Load the synthetic store into a *dedicated* Postgres database and run the real pipeline.

    python -m app.demo                      # -> <your db>_demo, seeded from DATABASE_URL credentials
    python -m app.demo --database-url postgresql+asyncpg://user:pw@host/db_demo --days 90

Safety: the target database name must end in ``_demo`` or ``_test`` - it is dropped and
recreated on every run, so it can never touch the database configured for real use.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date

import asyncpg
from sqlalchemy import Column, MetaData, Table, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import BigInteger, DateTime, String, Text, insert
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .generator import DemoConfig, generate

_tracker_meta = MetaData()
TRACKER_EVENTS = Table(
    "tracker_events_local", _tracker_meta,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("api_key", String(128), nullable=False),
    Column("event_name", String(100), nullable=False),
    Column("user_id", String(64), nullable=False),
    Column("url", Text, nullable=False),
    Column("timestamp", BigInteger, nullable=False),
    Column("metadata", JSONB, nullable=False),
    Column("synced_at", DateTime(timezone=True), nullable=False),
)


def demo_url_from(database_url: str, suffix: str = "_demo") -> str:
    """Same server/credentials as ``database_url``, database name ``<name><suffix>``."""
    url = make_url(database_url)
    name = url.database or "bi_shoper"
    for s in ("_demo", "_test"):
        name = name.removesuffix(s)
    return url.set(database=name + suffix).render_as_string(hide_password=False)


def assert_disposable(url: URL) -> None:
    if not (url.database or "").endswith(("_demo", "_test")):
        raise ValueError(f"Refusing to reset database {url.database!r}: name must end in _demo or _test")


async def _ensure_database(url: URL) -> None:
    conn = await asyncpg.connect(
        host=url.host, port=url.port or 5432, user=url.username, password=url.password, database="postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database):
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


async def seed_database(database_url: str, config: DemoConfig | None = None) -> dict[str, int]:
    """Drop + recreate the schema in a disposable database, load RAW rows, run RAW -> CORE."""
    import app.models  # noqa: F401  (registers every table on Base.metadata)
    from app.database import Base
    from app.migrations import upgrade_to_head
    from app.services.transform_service import TransformService

    url = make_url(database_url)
    assert_disposable(url)
    await _ensure_database(url)
    data = generate(config)

    engine = create_async_engine(url.set(drivername="postgresql+asyncpg"))
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        # The real migrations build the schema, so every seed (and every test run) exercises them.
        await asyncio.to_thread(upgrade_to_head, url.render_as_string(hide_password=False))
        async with engine.begin() as conn:
            await conn.run_sync(_tracker_meta.create_all)
            for name, rows in data.items():
                table = TRACKER_EVENTS if name == "tracker_events_local" else Base.metadata.tables[name]
                for i in range(0, len(rows), 5000):
                    await conn.execute(insert(table), rows[i:i + 5000])
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await TransformService(session).run_all()
    finally:
        await engine.dispose()
    return {name: len(rows) for name, rows in data.items()}


def main() -> None:
    from app.config import get_settings

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database-url", help="target (default: DATABASE_URL with the database name + _demo)")
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--tracker-days", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD, default today")
    a = p.parse_args()

    target = a.database_url or demo_url_from(get_settings().database_url)
    counts = asyncio.run(seed_database(
        target, DemoConfig(seed=a.seed, days=a.days, tracker_days=a.tracker_days, as_of=a.as_of)))
    print(f"Seeded {make_url(target).database}:")
    for name, n in counts.items():
        print(f"  {name:<24}{n:>8}")
    shown = make_url(target).render_as_string(hide_password=True)
    print(f"\nRun the API against it (with the real password):\n  DATABASE_URL={shown} uvicorn app.main:app --port 8010")


if __name__ == "__main__":
    main()
