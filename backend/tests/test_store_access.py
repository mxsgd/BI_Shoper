"""A request acts only for the store in its signed app session.

Runs against the real app (every router), with the database swapped for in-memory SQLite and the
client calling from a public address, as it would in production.
"""
import time
from types import SimpleNamespace

import httpx
import pytest_asyncio
from fastapi.routing import APIRoute

from app.config import get_settings
from app.database import get_db
from app.main import app
from app.models.store import Store
from app.routers import variant_codes
from app.routers.access import SESSION_COOKIE, current_session, require_admin
from app.services.price_update import price_update_jobs
from app.services.security.app_session import create_session_token
from tests.conftest import TEST_ADMIN_TOKEN, TEST_SECRET

PUBLIC_CLIENT = ("203.0.113.10", 50000)
LOCAL_CLIENT = ("127.0.0.1", 50000)

# Reachable without a session: both carry Shoper's own signature, plus the health check.
PUBLIC_ROUTES = {
    ("POST", "/api/shoper/app-store/event"),
    ("GET", "/api/shoper/app/entry"),
    ("GET", "/api/health"),
}


@pytest_asyncio.fixture
async def stores(session_maker):
    async with session_maker() as db:
        a = Store(name="shop-a", api_url="https://a.example.com/webapi/rest", api_token="")
        b = Store(name="shop-b", api_url="https://b.example.com/webapi/rest", api_token="")
        db.add_all([a, b])
        await db.commit()
        return a.id, b.id


@pytest_asyncio.fixture
async def make_client(session_maker):
    async def override_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    clients = []

    def make(client_addr=PUBLIC_CLIENT):
        c = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=client_addr), base_url="http://test")
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()
    app.dependency_overrides.pop(get_db, None)


def session_cookie(store_id: int, ttl: int = 1800, secret: str = TEST_SECRET) -> dict:
    token = create_session_token(store_id=store_id, shop_id=f"shop-{store_id}", secret=secret, ttl_seconds=ttl)
    return {"cookie": f"{SESSION_COOKIE}={token}"}


def _dependency_calls(dependant) -> set:
    found = set()
    for dep in dependant.dependencies:
        found.add(dep.call)
        found |= _dependency_calls(dep)
    return found


def test_every_route_requires_a_session_or_admin():
    """Guards new endpoints too: forgetting Depends(current_store_id) fails here."""
    open_routes = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        calls = _dependency_calls(route.dependant)
        if current_session in calls or require_admin in calls:
            continue
        open_routes |= {(m, route.path) for m in route.methods}
    assert open_routes == PUBLIC_ROUTES


async def test_no_session_is_401(make_client, stores):
    resp = await make_client().get("/api/price-update/jobs/latest")
    assert resp.status_code == 401


async def test_store_id_from_client_must_match_session(make_client, stores):
    a, b = stores
    client = make_client()
    resp = await client.get(f"/api/price-update/jobs/latest?store_id={b}", headers=session_cookie(a))
    assert resp.status_code == 403
    resp = await client.get(f"/api/stores/{b}/sync-status", headers=session_cookie(a))
    assert resp.status_code == 403
    resp = await client.post("/api/stores/sync-now", json={"store_id": b}, headers=session_cookie(a))
    assert resp.status_code == 403
    resp = await client.post(
        "/api/variant-codes/apply-codes/start",
        json={"store_id": b, "product_ids": [1], "option_groups": []},
        headers=session_cookie(a))
    assert resp.status_code == 403


async def test_session_endpoint_returns_session_store(make_client, stores):
    a, _ = stores
    resp = await make_client().get("/api/shoper/app/session", headers=session_cookie(a))
    assert resp.json() == {"store_id": a, "shop": f"shop-{a}"}


async def test_other_stores_variant_job_is_not_found(make_client, stores):
    a, b = stores
    variant_codes._apply_jobs["job-of-b"] = {"store_id": b, "status": "done", "log": []}
    try:
        client = make_client()
        assert (await client.get(
            "/api/variant-codes/apply-codes/jobs/job-of-b", headers=session_cookie(a))).status_code == 404
        assert (await client.get(
            "/api/variant-codes/apply-codes/jobs/job-of-b", headers=session_cookie(b))).status_code == 200
    finally:
        variant_codes._apply_jobs.pop("job-of-b", None)


async def test_other_stores_price_job_is_not_found(make_client, stores, monkeypatch):
    a, b = stores

    async def fake_get_job(job_id):
        return SimpleNamespace(job_id=job_id, store_id=b)

    async def fail_cancel(job_id):
        raise AssertionError("cancel must not run for another store's job")

    monkeypatch.setattr(price_update_jobs, "get_job", fake_get_job)
    monkeypatch.setattr(price_update_jobs, "cancel_job", fail_cancel)
    client = make_client()
    for method, path in [
        ("GET", "/api/price-update/jobs/j1"),
        ("POST", "/api/price-update/jobs/j1/cancel"),
        ("GET", "/api/price-update/jobs/j1/logs"),
        ("GET", "/api/price-update/jobs/j1/logs/export.csv"),
    ]:
        resp = await client.request(method, path, headers=session_cookie(a))
        assert resp.status_code == 404, path


async def test_admin_endpoints_need_the_admin_token(make_client, stores):
    a, _ = stores
    client = make_client()
    assert (await client.get("/api/stores/", headers=session_cookie(a))).status_code == 403
    assert (await client.get("/api/stores/", headers={"X-Admin-Token": "wrong"})).status_code == 403
    assert (await client.delete(f"/api/stores/{a}", headers=session_cookie(a))).status_code == 403
    assert (await client.put(
        "/api/settings/tracking", json={}, headers=session_cookie(a))).status_code == 403
    assert (await client.get("/api/stores/", headers={"X-Admin-Token": TEST_ADMIN_TOKEN})).status_code == 200


async def test_session_is_extended_when_half_used(make_client, stores):
    a, _ = stores
    client = make_client()
    fresh = await client.get("/api/shoper/app/session", headers=session_cookie(a, ttl=1800))
    assert SESSION_COOKIE not in fresh.cookies
    old = await client.get("/api/shoper/app/session", headers=session_cookie(a, ttl=600))
    assert old.cookies.get(SESSION_COOKIE)


async def test_session_is_not_extended_for_inactive_store(make_client, stores, session_maker):
    a, _ = stores
    async with session_maker() as db:
        (await db.get(Store, a)).is_active = False
        await db.commit()
    resp = await make_client().get("/api/shoper/app/session", headers=session_cookie(a, ttl=600))
    assert resp.status_code == 200  # still valid until it expires
    assert SESSION_COOKIE not in resp.cookies


async def test_expired_session_is_401(make_client, stores):
    a, _ = stores
    token = create_session_token(
        store_id=a, shop_id="s", secret=TEST_SECRET, ttl_seconds=60, now=time.time() - 3600)
    resp = await make_client().get("/api/shoper/app/session", headers={"cookie": f"{SESSION_COOKIE}={token}"})
    assert resp.status_code == 401


async def test_empty_secret_never_accepts_a_session(make_client, stores, monkeypatch):
    """With no secret configured, a token signed with an empty key must not pass."""
    a, _ = stores
    settings = get_settings()
    monkeypatch.setattr(settings, "shoper_session_secret", "")
    monkeypatch.setattr(settings, "shoper_app_secret", "")
    resp = await make_client().get("/api/shoper/app/session", headers=session_cookie(a, secret=""))
    assert resp.status_code == 401


async def test_dev_store_only_for_local_requests(make_client, stores, monkeypatch):
    a, _ = stores
    monkeypatch.setattr(get_settings(), "dev_store_id", a)
    local = await make_client(LOCAL_CLIENT).get("/api/shoper/app/session")
    assert local.json() == {"store_id": a, "shop": None}
    assert (await make_client(LOCAL_CLIENT).get("/api/stores/")).status_code == 200
    remote = await make_client(PUBLIC_CLIENT).get("/api/shoper/app/session")
    assert remote.status_code == 401
    assert (await make_client(PUBLIC_CLIENT).get("/api/stores/")).status_code == 403
