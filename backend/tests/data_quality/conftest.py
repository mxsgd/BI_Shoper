"""Seeds a disposable Postgres database once per session with the synthetic store.

Target: $TEST_DATABASE_URL, else <DATABASE_URL's database>_test on the same server.
If Postgres is unreachable the DB-backed tests are skipped locally; set REQUIRE_POSTGRES=1
(CI does) to make that a failure instead.
"""
import asyncio
import os
from datetime import date

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.demo.generator import DemoConfig
from app.demo.seed import demo_url_from, seed_database

# as_of is today: analytics services measure periods back from today, so a fixed past date would
# leave every window empty and let queries short-circuit on "no data" before reaching their SQL.
CONFIG = DemoConfig(seed=7, days=90, tracker_days=14, as_of=date.today())


@pytest.fixture(scope="session")
def demo_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or demo_url_from(get_settings().database_url, "_test")
    try:
        asyncio.run(seed_database(url, CONFIG))
    except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as exc:
        if os.environ.get("REQUIRE_POSTGRES"):
            raise
        pytest.skip(f"Postgres not available for data-quality tests: {exc}")
    return url


@pytest_asyncio.fixture
async def session(demo_db_url):
    engine = create_async_engine(demo_db_url, poolclass=NullPool)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()
