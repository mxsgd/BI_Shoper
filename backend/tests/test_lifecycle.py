"""Tests of the App Store lifecycle endpoint POST /api/shoper/app-store/event."""

import httpx
import pytest
import pytest_asyncio
import respx
from fastapi import FastAPI
from sqlalchemy import select

from app.database import get_db
from app.models.shoper_app_installation import ShoperAppInstallation
from app.models.store import Store
from app.routers.shoper_app import router
from tests.conftest import sign_params
from tests.test_partner_auth import SHOP_URL, TOKEN_URL, token_response

INSTALL_PARAMS = {
    "action": "install",
    "application_code": "bi-shoper",
    "application_version": "1",
    "auth_code": "one-time-auth-code",
    "shop": "shop-abc",
    "shop_url": SHOP_URL,
    "trial": "0",
}


@pytest_asyncio.fixture
async def client(session_maker):
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def post_event(client, params):
    return await client.post("/api/shoper/app-store/event", data=params)


@respx.mock
async def test_install_creates_store_and_installation(client, session_maker):
    respx.post(TOKEN_URL).mock(return_value=token_response())

    resp = await post_event(client, sign_params(INSTALL_PARAMS))

    assert resp.status_code == 200
    async with session_maker() as db:
        inst = (
            await db.execute(
                select(ShoperAppInstallation).where(
                    ShoperAppInstallation.shoper_shop_id == "shop-abc"
                )
            )
        ).scalar_one()
        assert inst.status == "active"
        assert inst.shop_url == SHOP_URL
        assert inst.application_version == 1
        assert inst.access_token_encrypted  # encrypted tokens stored
        store = await db.get(Store, inst.store_id)
        assert store.is_active
        assert store.api_url == f"{SHOP_URL}/webapi/rest"


@respx.mock
async def test_uninstall_deactivates(client, session_maker):
    respx.post(TOKEN_URL).mock(return_value=token_response())
    await post_event(client, sign_params(INSTALL_PARAMS))

    uninstall = {"action": "uninstall", "shop": "shop-abc", "shop_url": SHOP_URL}
    resp = await post_event(client, sign_params(uninstall))

    assert resp.status_code == 200
    async with session_maker() as db:
        inst = (
            await db.execute(
                select(ShoperAppInstallation).where(
                    ShoperAppInstallation.shoper_shop_id == "shop-abc"
                )
            )
        ).scalar_one()
        assert inst.status == "uninstalled"
        assert inst.access_token_encrypted is None
        assert inst.refresh_token_encrypted is None
        store = await db.get(Store, inst.store_id)
        assert store.is_active is False


async def test_unknown_action_controlled_4xx(client):
    resp = await post_event(
        client, sign_params({"action": "explode", "shop": "shop-abc"})
    )
    assert resp.status_code == 400


async def test_missing_required_fields(client):
    resp = await post_event(client, sign_params({"action": "install"}))
    assert resp.status_code == 400  # missing shop

    params = {k: v for k, v in INSTALL_PARAMS.items() if k != "shop_url"}
    resp = await post_event(client, sign_params(params))
    assert resp.status_code == 400  # missing shop_url on install


async def test_invalid_application_version_type(client):
    params = {**INSTALL_PARAMS, "application_version": "not-an-int"}
    resp = await post_event(client, sign_params(params))
    assert resp.status_code == 400


async def test_invalid_signature_rejected(client):
    params = sign_params(INSTALL_PARAMS)
    params["shop"] = "evil-shop"
    resp = await post_event(client, params)
    assert resp.status_code == 401


async def test_missing_signature_rejected(client):
    resp = await post_event(client, dict(INSTALL_PARAMS))
    assert resp.status_code == 401


@respx.mock
async def test_replayed_install_is_idempotent(client, session_maker):
    # First install succeeds.
    respx.post(TOKEN_URL).mock(return_value=token_response())
    resp1 = await post_event(client, sign_params(INSTALL_PARAMS))
    assert resp1.status_code == 200

    # Replay: the auth_code was consumed, Shoper would reject the exchange.
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    resp2 = await post_event(client, sign_params(INSTALL_PARAMS))
    assert resp2.status_code == 200  # idempotent - shop stays connected

    async with session_maker() as db:
        rows = (
            (await db.execute(select(ShoperAppInstallation))).scalars().all()
        )
        assert len(rows) == 1
        assert rows[0].status == "active"
        assert rows[0].access_token_encrypted  # old tokens kept


@respx.mock
async def test_reinstall_existing_shop_no_duplicate(client, session_maker):
    respx.post(TOKEN_URL).mock(return_value=token_response())
    await post_event(client, sign_params(INSTALL_PARAMS))
    await post_event(
        client, sign_params({**INSTALL_PARAMS, "auth_code": "new-code", "application_version": "2"})
    )

    async with session_maker() as db:
        rows = ((await db.execute(select(ShoperAppInstallation))).scalars().all())
        assert len(rows) == 1
        assert rows[0].application_version == 2
        stores = ((await db.execute(select(Store))).scalars().all())
        assert len(stores) == 1


@respx.mock
async def test_fresh_install_exchange_failure_409(client, session_maker):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    resp = await post_event(client, sign_params(INSTALL_PARAMS))
    assert resp.status_code == 409
    async with session_maker() as db:
        inst = (
            (await db.execute(select(ShoperAppInstallation))).scalars().one()
        )
        assert inst.access_token_encrypted is None  # no partial token state


async def test_install_without_auth_code(client):
    params = {k: v for k, v in INSTALL_PARAMS.items() if k != "auth_code"}
    resp = await post_event(client, sign_params(params))
    assert resp.status_code == 400


async def test_uninstall_unknown_shop_idempotent(client):
    resp = await post_event(
        client, sign_params({"action": "uninstall", "shop": "ghost-shop"})
    )
    assert resp.status_code == 200


@respx.mock
async def test_uninstalled_store_excluded_from_scheduler_query(client, session_maker):
    """After uninstall the scheduler's store selection must skip the store."""
    from app.scheduler.jobs import _stores_select

    respx.post(TOKEN_URL).mock(return_value=token_response())
    await post_event(client, sign_params(INSTALL_PARAMS))
    await post_event(client, sign_params({"action": "uninstall", "shop": "shop-abc"}))

    async with session_maker() as db:
        stores = ((await db.execute(_stores_select(None))).scalars().all())
        assert stores == []


@respx.mock
async def test_error_response_contains_no_secrets(client):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    resp = await post_event(client, sign_params(INSTALL_PARAMS))
    assert resp.status_code == 409
    body = resp.text
    assert "one-time-auth-code" not in body
    assert "test-secret" not in body


async def test_rejected_ssrf_shop_url(client):
    params = {**INSTALL_PARAMS, "shop_url": "https://127.0.0.1"}
    resp = await post_event(client, sign_params(params))
    assert resp.status_code == 400


@respx.mock
async def test_upgrade_updates_version(client, session_maker):
    respx.post(TOKEN_URL).mock(return_value=token_response())
    await post_event(client, sign_params(INSTALL_PARAMS))

    upgrade = {
        "action": "upgrade",
        "shop": "shop-abc",
        "application_version": "7",
    }
    resp = await post_event(client, sign_params(upgrade))
    assert resp.status_code == 200

    async with session_maker() as db:
        inst = (
            (await db.execute(select(ShoperAppInstallation))).scalars().one()
        )
        assert inst.application_version == 7


async def test_upgrade_unknown_shop_409(client):
    resp = await post_event(
        client,
        sign_params({"action": "upgrade", "shop": "ghost", "application_version": "2"}),
    )
    assert resp.status_code == 409
