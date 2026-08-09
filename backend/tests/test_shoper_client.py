"""Tests of ShoperClient auth behaviour (401 refresh, 429 retry, token binding)."""

import httpx
import pytest
import respx

from app.services.shoper_client import ShoperClient, ShoperUnauthorizedError

BASE = "https://shop-a.example.com/webapi/rest"


@respx.mock
async def test_request_uses_bearer_token():
    route = respx.get(f"{BASE}/orders").mock(
        return_value=httpx.Response(200, json={"list": []})
    )
    client = ShoperClient(BASE, "token-A", store_id=1)
    await client.get("/orders")
    await client.close()
    assert route.calls[0].request.headers["Authorization"] == "Bearer token-A"


@respx.mock
async def test_401_refresh_retry_success():
    calls = {"refresh": 0}

    async def refresh():
        calls["refresh"] += 1
        return "token-NEW"

    route = respx.get(f"{BASE}/orders")
    route.side_effect = [
        httpx.Response(401),
        httpx.Response(200, json={"list": [{"order_id": 1}]}),
    ]
    client = ShoperClient(BASE, "expired", on_unauthorized=refresh, store_id=1)
    result = await client.get("/orders")
    await client.close()

    assert calls["refresh"] == 1
    assert result == [{"order_id": 1}]
    assert route.calls[1].request.headers["Authorization"] == "Bearer token-NEW"


@respx.mock
async def test_second_401_no_second_refresh():
    calls = {"refresh": 0}

    async def refresh():
        calls["refresh"] += 1
        return "still-bad"

    respx.get(f"{BASE}/orders").mock(return_value=httpx.Response(401))
    client = ShoperClient(BASE, "expired", on_unauthorized=refresh, store_id=1)
    with pytest.raises(ShoperUnauthorizedError):
        await client.get("/orders")
    await client.close()
    assert calls["refresh"] == 1  # exactly one refresh, no 401→refresh loop


@respx.mock
async def test_429_respects_retry_after(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("app.services.shoper_client.asyncio.sleep", fake_sleep)
    route = respx.get(f"{BASE}/orders")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json={"list": []}),
    ]
    client = ShoperClient(BASE, "token", store_id=1)
    result = await client.get("/orders")
    await client.close()
    assert result == []
    assert 7 in sleeps


@respx.mock
async def test_timeout_returns_none_after_retries(monkeypatch):
    async def fake_sleep(_):
        return None

    monkeypatch.setattr("app.services.shoper_client.asyncio.sleep", fake_sleep)
    respx.get(f"{BASE}/orders").mock(side_effect=httpx.ConnectTimeout("boom"))
    client = ShoperClient(BASE, "token", store_id=1)
    result = await client.get_raw("/orders")
    await client.close()
    assert result is None


def test_set_token_rejects_other_store():
    client = ShoperClient(BASE, "token-A", store_id=1)
    with pytest.raises(ValueError, match="mismatch"):
        client.set_token("token-B", store_id=2)
    client.set_token("token-A2", store_id=1)  # same store OK
    assert client.token == "token-A2"


@respx.mock
async def test_two_stores_do_not_share_tokens():
    base_b = "https://shop-b.example.com/webapi/rest"
    route_a = respx.get(f"{BASE}/orders").mock(
        return_value=httpx.Response(200, json={"list": []})
    )
    route_b = respx.get(f"{base_b}/orders").mock(
        return_value=httpx.Response(200, json={"list": []})
    )
    client_a = ShoperClient(BASE, "token-A", store_id=1)
    client_b = ShoperClient(base_b, "token-B", store_id=2)
    await client_a.get("/orders")
    await client_b.get("/orders")
    await client_a.close()
    await client_b.close()
    assert route_a.calls[0].request.headers["Authorization"] == "Bearer token-A"
    assert route_b.calls[0].request.headers["Authorization"] == "Bearer token-B"


@respx.mock
async def test_pagination_preserved():
    route = respx.get(f"{BASE}/orders")
    route.side_effect = [
        httpx.Response(200, json={"list": [{"id": 1}], "pages": 2, "count": 2}),
        httpx.Response(200, json={"list": [{"id": 2}], "pages": 2, "count": 2}),
    ]
    client = ShoperClient(BASE, "token", store_id=1)
    items = await client.get_all("/orders")
    await client.close()
    assert [i["id"] for i in items] == [1, 2]
    assert route.call_count == 2


@respx.mock
async def test_post_and_put_methods():
    respx.post(f"{BASE}/products").mock(
        return_value=httpx.Response(201, json={"product_id": 5})
    )
    respx.put(f"{BASE}/products/5").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = ShoperClient(BASE, "token", store_id=1)
    created = await client.post("/products", {"code": "X"})
    updated, err = await client.put_with_error("/products/5", {"code": "Y"})
    await client.close()
    assert created == {"product_id": 5}
    assert updated == {"ok": True}
    assert err is None


@respx.mock
async def test_close_closes_http_client():
    respx.get(f"{BASE}/orders").mock(return_value=httpx.Response(200, json={"list": []}))
    client = ShoperClient(BASE, "token", store_id=1)
    await client.get("/orders")
    inner = client._client
    await client.close()
    assert inner.is_closed


def test_repr_and_errors_have_no_token():
    client = ShoperClient(BASE, "super-secret-token", store_id=1)
    assert "super-secret-token" not in repr(client)
    err = ShoperUnauthorizedError("GET /orders -> 401: unauthorized")
    assert "super-secret-token" not in str(err)
