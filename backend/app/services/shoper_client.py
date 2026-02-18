"""
Universal Shoper REST API client with retry, rate limiting, and pagination.
Based on battle-tested logic from MK-FOAM/Decorator migration.

Usage:
    client = ShoperClient(base_url="https://www.sklep-mkfoam.pl/webapi/rest", token="...")
    orders = await client.get_all("/orders")
    product = await client.get("/products/123")
"""

import json
import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_PER_PAGE = 50
DEFAULT_TIMEOUT = 15.0
MAX_RETRIES = 5
RETRY_DELAY = 5.0
RATE_DELAY = 0.2


class ShoperClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client: httpx.AsyncClient | None = None

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=DEFAULT_TIMEOUT,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get(self, endpoint: str, params: dict | None = None) -> Any:
        """Single GET with retry on 429 (rate limit)."""
        client = await self._get_client()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = await client.get(endpoint, params=params)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, dict) and "list" in data:
                        lst = data["list"]
                        if isinstance(lst, dict):
                            return list(lst.values())
                        return lst
                    return data
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", RETRY_DELAY))
                    logger.warning("Rate limited, waiting %ds (attempt %d)", wait, attempt)
                    await asyncio.sleep(wait)
                    continue
                logger.error("GET %s -> %d: %s", endpoint, r.status_code, r.text[:300])
                return None
            except httpx.TimeoutException:
                logger.warning("Timeout GET %s (attempt %d)", endpoint, attempt)
                await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error("Error GET %s: %s", endpoint, e)
                await asyncio.sleep(RETRY_DELAY)
        return None

    async def get_all(
        self,
        endpoint: str,
        params: dict | None = None,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> list[dict]:
        """Paginated GET collecting all items across pages."""
        params = dict(params or {})
        all_items: list[dict] = []
        page = 1

        while True:
            params["limit"] = per_page
            params["page"] = page
            data = await self.get(endpoint, params)
            if not data:
                break
            if isinstance(data, list):
                all_items.extend(data)
                if len(data) < per_page:
                    break
            else:
                all_items.append(data)
                break
            page += 1
            await asyncio.sleep(RATE_DELAY)

        return all_items

    async def get_filtered(
        self,
        endpoint: str,
        filters: dict,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> list[dict]:
        """GET with Shoper-style filters: filters=json.dumps({...})."""
        params = {"filters": json.dumps(filters)}
        return await self.get_all(endpoint, params=params, per_page=per_page)

    async def post(self, endpoint: str, body: dict) -> Any:
        """POST with retry logic."""
        client = await self._get_client()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = await client.post(endpoint, json=body)
                if r.status_code in (200, 201):
                    return r.json()
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", RETRY_DELAY))
                    await asyncio.sleep(wait)
                    continue
                logger.error("POST %s -> %d: %s", endpoint, r.status_code, r.text[:300])
                return None
            except httpx.TimeoutException:
                await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error("Error POST %s: %s", endpoint, e)
                await asyncio.sleep(RETRY_DELAY)
        return None

    async def put(self, endpoint: str, body: dict) -> Any:
        """PUT with retry logic."""
        client = await self._get_client()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = await client.put(endpoint, json=body)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", RETRY_DELAY))
                    await asyncio.sleep(wait)
                    continue
                logger.error("PUT %s -> %d: %s", endpoint, r.status_code, r.text[:300])
                return None
            except httpx.TimeoutException:
                await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error("Error PUT %s: %s", endpoint, e)
                await asyncio.sleep(RETRY_DELAY)
        return None
