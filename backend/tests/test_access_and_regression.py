"""Auth-mode dispatch, legacy gating and light regression checks."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.config import Settings
from app.models.shoper_app_installation import ShoperAppInstallation
from app.models.store import Store
from app.services.shoper_access import (
    AUTH_MODE_DISCONNECTED,
    AUTH_MODE_LEGACY,
    AUTH_MODE_PARTNER,
    StoreDisconnectedError,
    ensure_store_access_token,
    store_auth_mode,
)
from app.services.shoper_partner_auth import ShoperPartnerAuthService
from tests.test_partner_auth import SHOP_URL, TOKEN_URL, token_response


async def make_store(db, **kwargs):
    store = Store(
        name="legacy-shop",
        api_url=f"{SHOP_URL}/webapi/rest",
        api_token="",
        **kwargs,
    )
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return store


async def test_partner_mode_used_when_installation_active(db_session, settings):
    store = await make_store(db_session)
    svc = ShoperPartnerAuthService(db_session, settings)
    inst = ShoperAppInstallation(
        store_id=store.id,
        shoper_shop_id="shop-x",
        shop_url=SHOP_URL,
        access_token_encrypted=svc.cipher.encrypt("partner-token"),
        refresh_token_encrypted=svc.cipher.encrypt("partner-refresh"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(inst)
    await db_session.commit()

    assert await store_auth_mode(db_session, store) == AUTH_MODE_PARTNER
    token = await ensure_store_access_token(db_session, store)
    assert token == "partner-token"


async def test_appstore_store_never_falls_back_to_legacy(db_session, monkeypatch):
    """Even with legacy enabled and credentials set, an App Store shop with a
    broken installation must NOT use login/password."""
    monkeypatch.setenv("SHOPER_ENABLE_LEGACY_WEBAPI", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        store = await make_store(db_session, api_login="user", api_password="pass")
        inst = ShoperAppInstallation(
            store_id=store.id,
            shoper_shop_id="shop-y",
            shop_url=SHOP_URL,
            status="needs_reauth",
        )
        db_session.add(inst)
        await db_session.commit()

        with pytest.raises(StoreDisconnectedError):
            await ensure_store_access_token(db_session, store)
    finally:
        monkeypatch.setenv("SHOPER_ENABLE_LEGACY_WEBAPI", "0")
        get_settings.cache_clear()


async def test_disconnected_when_no_install_and_legacy_disabled(db_session):
    store = await make_store(db_session, api_login="user", api_password="pass")
    assert await store_auth_mode(db_session, store) == AUTH_MODE_DISCONNECTED
    with pytest.raises(StoreDisconnectedError):
        await ensure_store_access_token(db_session, store)


async def test_legacy_mode_when_flag_enabled(db_session, monkeypatch):
    monkeypatch.setenv("SHOPER_ENABLE_LEGACY_WEBAPI", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        store = await make_store(db_session, api_login="user", api_password="pass")
        assert await store_auth_mode(db_session, store) == AUTH_MODE_LEGACY
    finally:
        monkeypatch.setenv("SHOPER_ENABLE_LEGACY_WEBAPI", "0")
        get_settings.cache_clear()


@respx.mock
async def test_partner_token_refresh_through_dispatcher(db_session, settings):
    store = await make_store(db_session)
    svc = ShoperPartnerAuthService(db_session, settings)
    inst = ShoperAppInstallation(
        store_id=store.id,
        shoper_shop_id="shop-z",
        shop_url=SHOP_URL,
        access_token_encrypted=svc.cipher.encrypt("stale"),
        refresh_token_encrypted=svc.cipher.encrypt("refresh-1"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(inst)
    await db_session.commit()

    respx.post(TOKEN_URL).mock(return_value=token_response(access="renewed"))
    token = await ensure_store_access_token(db_session, store)
    assert token == "renewed"


# ----------------------------------------------------------------------
# Regression: modules that depend on Shoper auth still import and wire up
# ----------------------------------------------------------------------
def test_app_and_services_import():
    from app.main import app  # noqa: F401
    from app.services.sync_service import SyncService  # noqa: F401
    from app.services.price_update import price_update_jobs  # noqa: F401
    from app.routers import variant_codes  # noqa: F401
    from app.scheduler import jobs  # noqa: F401


def test_all_expected_routes_registered():
    from app.main import app

    paths = {route.path for route in app.routes}
    expected = {
        "/api/shoper/app-store/event",
        "/api/shoper/app/entry",
        "/api/shoper/app/session",
        "/api/price-update/jobs",
        "/api/analytics/overview",
        "/api/stores/sync-now",
    }
    assert expected.issubset(paths)


async def test_sync_service_builds_bound_client(db_session):
    from app.services.sync_service import SyncService

    store = await make_store(db_session)
    svc = SyncService(db_session, store)
    assert svc.client.store_id == store.id
    await svc.close()


async def test_stores_endpoint_returns_no_secrets(session_maker, monkeypatch):
    import httpx
    from fastapi import FastAPI

    from app.database import get_db
    from app.routers.stores import router

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    async with session_maker() as db:
        await make_store(db, api_login="secret-login", api_password="secret-pass")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/api/stores/")
    assert resp.status_code == 200
    body = resp.text
    assert "secret-login" not in body
    assert "secret-pass" not in body
    assert "api_token" not in {k for row in resp.json() for k in row}
    assert resp.json()[0]["auth_mode"] == AUTH_MODE_DISCONNECTED


async def test_stores_patch_rejects_legacy_credentials_when_disabled(session_maker):
    import httpx
    from fastapi import FastAPI

    from app.database import get_db
    from app.routers.stores import router

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    async with session_maker() as db:
        store = await make_store(db)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.patch(
            f"/api/stores/{store.id}/auth",
            json={"api_login": "u", "api_password": "p"},
        )
    assert resp.status_code == 400
