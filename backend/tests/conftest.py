import hashlib
import hmac
import os
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

TEST_APP_ID = "test-app-id"
TEST_SECRET = "test-secret"
TEST_CIPHER_KEY = Fernet.generate_key().decode()
TEST_ADMIN_TOKEN = "test-admin-token"

# Environment must be prepared BEFORE app settings are instantiated anywhere.
# DATABASE_URL is required by Settings. Fall back to a dummy (lazy engine, never connects) only when
# neither the environment nor backend/.env provides one - an env var would otherwise beat the .env file.
_env_file = Path(__file__).resolve().parents[1] / ".env"
_env_has_url = _env_file.exists() and any(
    line.startswith("DATABASE_URL=") for line in _env_file.read_text(encoding="utf-8").splitlines()
)
if not _env_has_url:
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:CHANGE_ME@localhost:5432/bi_shoper")
os.environ["SHOPER_APPSTORE_ENABLED"] = "1"
os.environ["SHOPER_APP_ID"] = TEST_APP_ID
os.environ["SHOPER_APP_SECRET"] = TEST_SECRET
os.environ["SHOPER_TOKEN_CIPHER_KEY"] = TEST_CIPHER_KEY
os.environ["SHOPER_ENABLE_LEGACY_WEBAPI"] = "0"
os.environ["SHOPER_ALLOW_INSECURE_SHOP_URL"] = "0"
os.environ["ADMIN_API_TOKEN"] = TEST_ADMIN_TOKEN

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.database import Base  # noqa: E402
from app.models.store import Store  # noqa: E402
from app.models.shoper_app_installation import ShoperAppInstallation  # noqa: E402


def sign_params(params: dict[str, str], secret: str = TEST_SECRET) -> dict[str, str]:
    """Compute the Shoper HMAC for params and return them with `hash` added."""
    filtered = {k: str(v) for k, v in params.items() if k != "hash"}
    canonical = "&".join(f"{k}={filtered[k]}" for k in sorted(filtered))
    digest = hmac.new(secret.encode(), canonical.encode(), hashlib.sha512).hexdigest()
    return {**params, "hash": digest}


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[Store.__table__, ShoperAppInstallation.__table__],
            )
        )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def session_maker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
def settings():
    return get_settings()
