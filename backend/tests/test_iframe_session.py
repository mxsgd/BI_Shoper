"""Tests of iframe entry verification and app sessions."""

import time

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.database import get_db
from app.models.shoper_app_installation import ShoperAppInstallation
from app.models.store import Store
from app.routers.shoper_app import SESSION_COOKIE, router
from app.services.security.app_session import (
    AppSessionError,
    create_session_token,
    verify_session_token,
)
from tests.conftest import sign_params

SHOP_ID = "shop-iframe-1"


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


async def install_shop(session_maker, *, status="active", store_active=True):
    async with session_maker() as db:
        store = Store(
            name=SHOP_ID,
            api_url="https://myshop.example.com/webapi/rest",
            api_token="",
            is_active=store_active,
        )
        db.add(store)
        await db.flush()
        inst = ShoperAppInstallation(
            store_id=store.id,
            shoper_shop_id=SHOP_ID,
            shop_url="https://myshop.example.com",
            status=status,
        )
        db.add(inst)
        await db.commit()
        return store.id


def iframe_params(**overrides):
    params = {
        "place": "adminMenu",
        "shop": SHOP_ID,
        "timestamp": str(int(time.time())),
    }
    params.update(overrides)
    return sign_params(params)


async def test_valid_iframe_entry_sets_session(client, session_maker):
    store_id = await install_shop(session_maker)
    resp = await client.get("/api/shoper/app/entry", params=iframe_params())
    assert resp.status_code == 302
    cookie = resp.cookies.get(SESSION_COOKIE)
    assert cookie
    set_cookie_header = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie_header
    assert "secure" in set_cookie_header
    assert "samesite=none" in set_cookie_header
    # session resolves to the correct local store, without any Shoper tokens
    session_resp = await client.get(
        "/api/shoper/app/session", cookies={SESSION_COOKIE: cookie}
    )
    assert session_resp.status_code == 200
    assert session_resp.json() == {"store_id": store_id, "shop": SHOP_ID}
    assert "token" not in session_resp.text.lower()


async def test_iframe_without_signature_rejected(client, session_maker):
    await install_shop(session_maker)
    params = iframe_params()
    params.pop("hash")
    resp = await client.get("/api/shoper/app/entry", params=params)
    assert resp.status_code == 401


async def test_iframe_tampered_shop_rejected(client, session_maker):
    await install_shop(session_maker)
    params = iframe_params()
    params["shop"] = "other-shop"  # tampered after signing
    resp = await client.get("/api/shoper/app/entry", params=params)
    assert resp.status_code == 401


async def test_iframe_expired_timestamp_rejected(client, session_maker):
    await install_shop(session_maker)
    params = iframe_params(timestamp=str(int(time.time()) - 3600))
    resp = await client.get("/api/shoper/app/entry", params=params)
    assert resp.status_code == 401


async def test_iframe_replay_within_window_same_signature(client, session_maker):
    """Lifecycle protocol has no nonce; replay within the timestamp window is
    accepted by design, but after the window it must be rejected."""
    await install_shop(session_maker)
    params = iframe_params(timestamp=str(int(time.time()) - 301))
    resp = await client.get("/api/shoper/app/entry", params=params)
    assert resp.status_code == 401


async def test_iframe_uninstalled_shop_rejected(client, session_maker):
    await install_shop(session_maker, status="uninstalled")
    resp = await client.get("/api/shoper/app/entry", params=iframe_params())
    assert resp.status_code == 403


async def test_iframe_unknown_shop_rejected(client):
    resp = await client.get("/api/shoper/app/entry", params=iframe_params())
    assert resp.status_code == 403


async def test_session_endpoint_without_cookie_401(client):
    resp = await client.get("/api/shoper/app/session")
    assert resp.status_code == 401


def test_session_token_roundtrip_and_expiry():
    token = create_session_token(
        store_id=7, shop_id="s1", secret="k", ttl_seconds=60, now=1000.0
    )
    payload = verify_session_token(token, secret="k", now=1030.0)
    assert payload["store_id"] == 7
    with pytest.raises(AppSessionError):
        verify_session_token(token, secret="k", now=1061.0)  # expired
    with pytest.raises(AppSessionError):
        verify_session_token(token, secret="other", now=1030.0)  # wrong key
    with pytest.raises(AppSessionError):
        verify_session_token(token + "x", secret="k", now=1030.0)  # tampered


def test_session_store_id_cannot_be_forged():
    token = create_session_token(
        store_id=7, shop_id="s1", secret="k", ttl_seconds=60, now=1000.0
    )
    payload_b64, _, sig = token.rpartition(".")
    # attacker swaps the payload for one pointing at another store
    forged = create_session_token(
        store_id=999, shop_id="s1", secret="wrong", ttl_seconds=60, now=1000.0
    )
    forged_payload = forged.rpartition(".")[0]
    with pytest.raises(AppSessionError):
        verify_session_token(f"{forged_payload}.{sig}", secret="k", now=1030.0)
