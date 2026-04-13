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

DEFAULT_PER_PAGE = 100
DEFAULT_TIMEOUT = 15.0
MAX_RETRIES = 5
RETRY_DELAY = 5.0
RATE_DELAY = 0.35


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

    async def get_raw(self, endpoint: str, params: dict | None = None) -> dict | list | None:
        """Single GET returning full JSON response (with metadata like count/pages)."""
        client = await self._get_client()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await asyncio.sleep(RATE_DELAY)
                r = await client.get(endpoint, params=params)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", RETRY_DELAY))
                    logger.warning("Rate limited, waiting %ds (attempt %d)", wait, attempt)
                    await asyncio.sleep(wait)
                    continue
                if (
                    r.status_code == 400
                    and endpoint == "/special-offers"
                    and "Missing MODULE 'special-offers'" in r.text
                ):
                    logger.info("Skipping %s for this store (module not enabled)", endpoint)
                    return []
                logger.error("GET %s -> %d: %s", endpoint, r.status_code, r.text[:300])
                return None
            except httpx.TimeoutException:
                logger.warning("Timeout GET %s (attempt %d)", endpoint, attempt)
                await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error("Error GET %s: %s", endpoint, e)
                await asyncio.sleep(RETRY_DELAY)
        return None

    async def get(self, endpoint: str, params: dict | None = None) -> Any:
        """Single GET with retry on 429 (rate limit). Returns extracted list/item."""
        data = await self.get_raw(endpoint, params)
        if data is None:
            return None
        if isinstance(data, dict) and "list" in data:
            lst = data["list"]
            if isinstance(lst, dict):
                return list(lst.values())
            return lst
        return data

    async def get_all(
        self,
        endpoint: str,
        params: dict | None = None,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> list[dict]:
        """Paginated GET collecting all items across pages.

        Uses the ``pages`` / ``count`` metadata returned by Shoper instead of
        comparing list length to ``per_page`` (API may return fewer items than
        requested per page).
        """
        params = dict(params or {})
        all_items: list[dict] = []
        page = 1
        total_pages: int | None = None

        while True:
            params["limit"] = per_page
            params["page"] = page
            raw = await self.get_raw(endpoint, params)
            if raw is None:
                break

            if isinstance(raw, dict) and "list" in raw:
                lst = raw["list"]
                if isinstance(lst, dict):
                    items = list(lst.values())
                elif isinstance(lst, list):
                    items = lst
                else:
                    break
                all_items.extend(items)
                total_pages = int(raw.get("pages", 1))
                if page >= total_pages:
                    break
            elif isinstance(raw, list):
                all_items.extend(raw)
                if len(raw) < per_page:
                    break
            else:
                all_items.append(raw)
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
