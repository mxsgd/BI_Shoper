"""Tests of ShoperPartnerAuthService (token exchange / refresh / rotation)."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.models.shoper_app_installation import (
    INSTALLATION_ACTIVE,
    INSTALLATION_NEEDS_REAUTH,
    ShoperAppInstallation,
)
from app.models.store import Store
from app.services.shoper_partner_auth import (
    InstallationNotConnectedError,
    ShoperPartnerAuthService,
    TokenEndpointError,
    TokenRequestRejectedError,
)

SHOP_URL = "https://myshop.example.com"
TOKEN_URL = f"{SHOP_URL}/webapi/rest/oauth/token"


def token_response(access="acc-token-1", refresh="ref-token-1", expires_in=7776000):
    return httpx.Response(
        200,
        json={
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": expires_in,
            "token_type": "bearer",
            "scope": "orders_read products_read",
        },
    )


async def make_installation(db, *, with_tokens=False, service=None, status=INSTALLATION_ACTIVE):
    store = Store(name="shop", api_url=f"{SHOP_URL}/webapi/rest", api_token="")
    db.add(store)
    await db.flush()
    inst = ShoperAppInstallation(
        store_id=store.id,
        shoper_shop_id=f"shop-{store.id}",
        shop_url=SHOP_URL,
        status=status,
    )
    if with_tokens and service is not None:
        inst.access_token_encrypted = service.cipher.encrypt("old-access")
        inst.refresh_token_encrypted = service.cipher.encrypt("old-refresh")
        inst.token_expires_at = datetime.now(timezone.utc) + timedelta(days=60)
        inst.token_updated_at = datetime.now(timezone.utc)
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst


@pytest.fixture
def service(db_session, settings):
    return ShoperPartnerAuthService(db_session, settings)


@respx.mock
async def test_exchange_auth_code_success(db_session, service):
    inst = await make_installation(db_session)
    route = respx.post(TOKEN_URL).mock(return_value=token_response())

    token = await service.exchange_auth_code(inst, "one-time-code")

    assert token == "acc-token-1"
    request = route.calls[0].request
    body = request.content.decode()
    assert "grant_type=authorization_code" in body
    assert "code=one-time-code" in body
    assert request.headers["Authorization"].startswith("Basic ")
    # tokens stored encrypted, never plaintext
    assert inst.access_token_encrypted != "acc-token-1"
    assert service.cipher.decrypt(inst.access_token_encrypted) == "acc-token-1"
    assert service.cipher.decrypt(inst.refresh_token_encrypted) == "ref-token-1"
    assert inst.token_expires_at is not None


@respx.mock
async def test_refresh_success_and_rotation(db_session, service):
    inst = await make_installation(db_session, with_tokens=True, service=service)
    respx.post(TOKEN_URL).mock(
        return_value=token_response(access="acc-2", refresh="ref-2")
    )

    token = await service.refresh_access_token(inst)

    assert token == "acc-2"
    # rotation: the NEW refresh token replaced the old one
    assert service.cipher.decrypt(inst.refresh_token_encrypted) == "ref-2"


@respx.mock
async def test_refresh_sends_stored_refresh_token(db_session, service):
    inst = await make_installation(db_session, with_tokens=True, service=service)
    route = respx.post(TOKEN_URL).mock(return_value=token_response())
    await service.refresh_access_token(inst)
    body = route.calls[0].request.content.decode()
    assert "grant_type=refresh_token" in body
    assert "refresh_token=old-refresh" in body


@respx.mock
async def test_missing_access_token_in_response(db_session, service):
    inst = await make_installation(db_session)
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"refresh_token": "r", "expires_in": 100})
    )
    with pytest.raises(TokenEndpointError, match="access_token"):
        await service.exchange_auth_code(inst, "code")


@respx.mock
async def test_missing_refresh_token_in_response(db_session, service):
    inst = await make_installation(db_session)
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 100})
    )
    with pytest.raises(TokenEndpointError, match="refresh_token"):
        await service.exchange_auth_code(inst, "code")


@respx.mock
async def test_invalid_json_response(db_session, service):
    inst = await make_installation(db_session)
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, content=b"<html>oops</html>", headers={"Content-Type": "application/json"}
        )
    )
    with pytest.raises(TokenEndpointError, match="invalid JSON"):
        await service.exchange_auth_code(inst, "code")


@respx.mock
async def test_non_json_content_type(db_session, service):
    inst = await make_installation(db_session)
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, content=b"ok", headers={"Content-Type": "text/html"}
        )
    )
    with pytest.raises(TokenEndpointError, match="Content-Type"):
        await service.exchange_auth_code(inst, "code")


@respx.mock
async def test_timeout_is_transient_error(db_session, service, monkeypatch):
    monkeypatch.setattr("app.services.shoper_partner_auth._TRANSIENT_BACKOFF", 0.0)
    inst = await make_installation(db_session)
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectTimeout("timeout"))
    with pytest.raises(TokenEndpointError):
        await service.exchange_auth_code(inst, "code")


@respx.mock
async def test_http_400_not_retried(db_session, service):
    inst = await make_installation(db_session)
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_request"})
    )
    with pytest.raises(TokenRequestRejectedError):
        await service.exchange_auth_code(inst, "code")
    assert route.call_count == 1  # authorization errors are never retried


@respx.mock
async def test_http_401_not_retried(db_session, service):
    inst = await make_installation(db_session)
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"})
    )
    with pytest.raises(TokenRequestRejectedError):
        await service.exchange_auth_code(inst, "code")
    assert route.call_count == 1


@respx.mock
async def test_http_429_retried_then_succeeds(db_session, service, monkeypatch):
    monkeypatch.setattr("app.services.shoper_partner_auth._TRANSIENT_BACKOFF", 0.0)
    inst = await make_installation(db_session)
    route = respx.post(TOKEN_URL)
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        token_response(),
    ]
    token = await service.exchange_auth_code(inst, "code")
    assert token == "acc-token-1"
    assert route.call_count == 2


@respx.mock
async def test_http_500_retried_bounded(db_session, service, monkeypatch):
    monkeypatch.setattr("app.services.shoper_partner_auth._TRANSIENT_BACKOFF", 0.0)
    inst = await make_installation(db_session)
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(TokenEndpointError):
        await service.exchange_auth_code(inst, "code")
    assert route.call_count == 3  # 1 + 2 bounded retries, no infinite loop


@respx.mock
async def test_fresh_token_no_refresh_request(db_session, service):
    inst = await make_installation(db_session, with_tokens=True, service=service)
    route = respx.post(TOKEN_URL).mock(return_value=token_response())
    token = await service.ensure_store_access_token(inst)
    assert token == "old-access"
    assert route.call_count == 0


@respx.mock
async def test_token_in_safety_window_triggers_refresh(db_session, service):
    inst = await make_installation(db_session, with_tokens=True, service=service)
    inst.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await db_session.commit()
    route = respx.post(TOKEN_URL).mock(return_value=token_response(access="fresh-acc"))
    token = await service.ensure_store_access_token(inst)
    assert token == "fresh-acc"
    assert route.call_count == 1


async def test_missing_refresh_token_raises(db_session, service):
    inst = await make_installation(db_session)
    with pytest.raises(InstallationNotConnectedError):
        await service.refresh_access_token(inst)


@respx.mock
async def test_invalid_grant_marks_needs_reauth(db_session, service):
    inst = await make_installation(db_session, with_tokens=True, service=service)
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(TokenRequestRejectedError):
        await service.refresh_access_token(inst)
    assert inst.status == INSTALLATION_NEEDS_REAUTH
    assert inst.last_auth_error == "invalid_grant"


@respx.mock
async def test_concurrent_refresh_single_request(db_engine, session_maker, settings):
    async with session_maker() as setup_db:
        svc0 = ShoperPartnerAuthService(setup_db, settings)
        inst = await make_installation(setup_db, with_tokens=True, service=svc0)
        inst.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)  # in window
        await setup_db.commit()
        inst_id = inst.id

    route = respx.post(TOKEN_URL).mock(return_value=token_response(access="fresh"))

    async def one_call():
        async with session_maker() as db:
            svc = ShoperPartnerAuthService(db, settings)
            row = await db.get(ShoperAppInstallation, inst_id)
            return await svc.ensure_store_access_token(row)

    results = await asyncio.gather(one_call(), one_call(), one_call())

    assert set(results) == {"fresh"}
    assert route.call_count == 1  # per-store lock: only one hit on the endpoint


async def test_inactive_installation_rejected(db_session, service):
    inst = await make_installation(db_session, status="uninstalled")
    with pytest.raises(InstallationNotConnectedError):
        await service.ensure_store_access_token(inst)


@respx.mock
async def test_no_partial_state_after_store_error(
    db_session, service, session_maker, monkeypatch
):
    inst = await make_installation(db_session, with_tokens=True, service=service)
    inst_id = inst.id
    old_access = inst.access_token_encrypted
    respx.post(TOKEN_URL).mock(return_value=token_response(access="new-acc"))

    real_commit = db_session.commit

    async def failing_commit():
        await db_session.rollback()  # simulate a failed flush/commit
        raise RuntimeError("db down")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    with pytest.raises(RuntimeError, match="db down"):
        await service.refresh_access_token(inst)
    monkeypatch.setattr(db_session, "commit", real_commit)

    # nothing was persisted - a fresh session sees the old encrypted value
    async with session_maker() as verify_db:
        fresh = await verify_db.get(ShoperAppInstallation, inst_id)
        assert fresh.access_token_encrypted == old_access


@respx.mock
async def test_rejected_error_has_no_secret_material(db_session, service):
    inst = await make_installation(db_session)
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            400, json={"error": "invalid_request", "echo": "code-echo-XYZ"}
        )
    )
    with pytest.raises(TokenRequestRejectedError) as exc_info:
        await service.exchange_auth_code(inst, "super-secret-auth-code")
    message = str(exc_info.value)
    assert "super-secret-auth-code" not in message
    assert "code-echo-XYZ" not in message
