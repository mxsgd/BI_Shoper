# How to run locally:
#   cd tracker
#   pip install -r requirements.txt
#   uvicorn app.main:app --reload --port 8001

import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

CONNECT_TIMEOUT_SECONDS = 5


def _build_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:2402@localhost:5432/bi_shoper")
    # Railway gives postgresql:// — asyncpg needs postgresql+asyncpg://
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _build_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    # Fail fast when Postgres is offline so app startup can continue to /health.
    connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
