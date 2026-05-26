"""
Scheduled sync jobs using APScheduler.
Runs order sync hourly, products every 6h, customers daily.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from ..database import async_session
from ..models.store import Store
from ..services.sync_service import SyncService
from ..services.transform_service import TransformService
from ..services.ga4_client import GA4SyncService

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_sync_statuses: dict[str, dict] = {}
_sync_locks: dict[str, asyncio.Lock] = {}


def _sync_key(store_id: int | None) -> str:
    return "all" if store_id is None else str(store_id)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_sync_lock(store_id: int | None) -> asyncio.Lock:
    key = _sync_key(store_id)
    lock = _sync_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _sync_locks[key] = lock
    return lock


def get_sync_status(store_id: int | None) -> dict:
    key = _sync_key(store_id)
    status = _sync_statuses.get(key)
    if status is None and store_id is not None:
        global_status = _sync_statuses.get("all")
        if global_status and global_status.get("status") == "running":
            status = global_status
    if status is None:
        return {
            "store_id": store_id,
            "scope": None,
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "error": None,
            "result": None,
        }
    return dict(status)


def _stores_select(store_id: int | None):
    q = select(Store).where(Store.is_active.is_(True))
    if store_id is not None:
        q = q.where(Store.id == store_id)
    return q.order_by(Store.name)


async def run_orders_sync(store_id: int | None = None) -> list[dict]:
    """Sync orders (and RAW orders / order items) for active store(s)."""
    results: list[dict] = []
    async with async_session() as db:
        stores = (await db.execute(_stores_select(store_id))).scalars().all()
        for store in stores:
            try:
                svc = SyncService(db, store)
                count = await svc.sync_orders(since=store.last_sync_orders)
                store.last_sync_orders = datetime.now(timezone.utc)
                await db.commit()
                await svc.close()
                logger.info("Orders sync done for %s: %d", store.name, count)
                results.append(
                    {"store_id": store.id, "name": store.name, "synced": count, "ok": True}
                )
            except Exception as e:
                logger.error("Orders sync failed for %s: %s", store.name, e)
                results.append(
                    {
                        "store_id": store.id,
                        "name": store.name,
                        "synced": 0,
                        "ok": False,
                        "error": str(e),
                    }
                )
    return results


async def run_products_sync(store_id: int | None = None) -> list[dict]:
    """Sync products (legacy + RAW) for active store(s)."""
    results: list[dict] = []
    async with async_session() as db:
        stores = (await db.execute(_stores_select(store_id))).scalars().all()
        for store in stores:
            try:
                svc = SyncService(db, store)
                count = await svc.sync_products()
                store.last_sync_products = datetime.now(timezone.utc)
                await db.commit()
                await svc.close()
                logger.info("Products sync done for %s: %d", store.name, count)
                results.append(
                    {"store_id": store.id, "name": store.name, "synced": count, "ok": True}
                )
            except Exception as e:
                logger.error("Products sync failed for %s: %s", store.name, e)
                results.append(
                    {
                        "store_id": store.id,
                        "name": store.name,
                        "synced": 0,
                        "ok": False,
                        "error": str(e),
                    }
                )
    return results


async def run_customers_sync(store_id: int | None = None) -> list[dict]:
    """Sync customers (legacy + RAW) for active store(s)."""
    results: list[dict] = []
    async with async_session() as db:
        stores = (await db.execute(_stores_select(store_id))).scalars().all()
        for store in stores:
            try:
                svc = SyncService(db, store)
                count = await svc.sync_customers()
                store.last_sync_customers = datetime.now(timezone.utc)
                await db.commit()
                await svc.close()
                logger.info("Customers sync done for %s: %d", store.name, count)
                results.append(
                    {"store_id": store.id, "name": store.name, "synced": count, "ok": True}
                )
            except Exception as e:
                logger.error("Customers sync failed for %s: %s", store.name, e)
                results.append(
                    {
                        "store_id": store.id,
                        "name": store.name,
                        "synced": 0,
                        "ok": False,
                        "error": str(e),
                    }
                )
    return results


async def run_reference_sync(store_id: int | None = None) -> list[dict]:
    """Sync reference data (payments, shipments, categories, discounts) for active store(s)."""
    results: list[dict] = []
    async with async_session() as db:
        stores = (await db.execute(_stores_select(store_id))).scalars().all()
        for store in stores:
            try:
                svc = SyncService(db, store)
                pay = await svc.sync_payments()
                ship = await svc.sync_shipments()
                cat = await svc.sync_categories()
                stat = await svc.sync_statuses()
                disc = await svc.sync_discounts()
                prod = await svc.sync_producers()
                tax = await svc.sync_taxes()
                pstk = await svc.sync_product_stocks()
                parc = await svc.sync_parcels()
                ugrp = await svc.sync_user_groups()
                curr = await svc.sync_currencies()
                subs = await svc.sync_subscribers()
                ctree = await svc.sync_categories_tree()
                await svc.close()
                total = pay + ship + cat + stat + disc + prod + tax + pstk + parc + ugrp + curr + subs + ctree
                logger.info(
                    "Reference sync done for %s: payments=%d, shipments=%d, "
                    "categories=%d, statuses=%d, discounts=%d, producers=%d, "
                    "taxes=%d, stocks=%d, parcels=%d, user_groups=%d, "
                    "currencies=%d, subscribers=%d, cat_tree=%d",
                    store.name, pay, ship, cat, stat, disc,
                    prod, tax, pstk, parc, ugrp, curr, subs, ctree,
                )
                results.append(
                    {
                        "store_id": store.id,
                        "name": store.name,
                        "synced": total,
                        "ok": True,
                        "detail": {
                            "payments": pay,
                            "shipments": ship,
                            "categories": cat,
                            "statuses": stat,
                            "discounts": disc,
                            "producers": prod,
                            "taxes": tax,
                            "product_stocks": pstk,
                            "parcels": parc,
                            "user_groups": ugrp,
                            "currencies": curr,
                            "subscribers": subs,
                            "categories_tree": ctree,
                        },
                    }
                )
            except Exception as e:
                logger.error("Reference sync failed for %s: %s", store.name, e)
                results.append(
                    {
                        "store_id": store.id,
                        "name": store.name,
                        "synced": 0,
                        "ok": False,
                        "error": str(e),
                    }
                )
    return results


async def sync_all_stores_orders():
    await run_orders_sync(None)


async def sync_all_stores_products():
    await run_products_sync(None)


async def sync_all_stores_customers():
    await run_customers_sync(None)


async def sync_all_stores_reference():
    await run_reference_sync(None)


async def run_transform() -> dict:
    """Run RAW -> CORE transforms."""
    async with async_session() as db:
        try:
            svc = TransformService(db)
            return await svc.run_all()
        except Exception as e:
            logger.error("Transform failed: %s", e)
            return {"ok": False, "error": str(e)}


async def transform_core():
    await run_transform()


async def run_ga4_sync() -> dict:
    """Pull GA4 data for today and yesterday into raw_ga4_* tables."""
    async with async_session() as db:
        try:
            svc = GA4SyncService(db)
            today = datetime.now(timezone.utc).date()
            yesterday = today - timedelta(days=1)
            yesterday_result = await svc.sync_day(yesterday)
            today_result = await svc.sync_day(today)
            return {
                "ok": bool(yesterday_result.get("ok")) and bool(today_result.get("ok")),
                "dates": {
                    str(yesterday): yesterday_result,
                    str(today): today_result,
                },
            }
        except Exception as e:
            logger.error("GA4 sync failed: %s", e)
            return {"ok": False, "error": str(e)}


async def run_ga4_backfill() -> dict:
    """Backfill last 90 days of GA4 data if tables are empty."""
    async with async_session() as db:
        try:
            svc = GA4SyncService(db)
            return await svc.backfill(90)
        except Exception as e:
            logger.error("GA4 backfill failed: %s", e)
            return {"ok": False, "error": str(e)}


async def sync_ga4_hourly():
    await run_ga4_sync()


SyncScope = Literal["all", "orders", "products", "customers", "reference", "transform", "ga4"]


async def run_sync_now(
    store_id: int | None = None, scope: SyncScope = "all"
) -> dict:
    """Run one or more sync phases; used by scheduler hooks and HTTP API."""
    lock = _get_sync_lock(store_id)
    if lock.locked():
        return {
            "already_running": True,
            **get_sync_status(store_id),
        }

    started_at = _now_iso()
    _sync_statuses[_sync_key(store_id)] = {
        "store_id": store_id,
        "scope": scope,
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "error": None,
        "result": None,
    }

    async with lock:
        try:
            out: dict = {"scope": scope, "store_id": store_id}
            if scope in ("all", "orders"):
                out["orders"] = await run_orders_sync(store_id)
            if scope in ("all", "products"):
                out["products"] = await run_products_sync(store_id)
            if scope in ("all", "customers"):
                out["customers"] = await run_customers_sync(store_id)
            if scope in ("all", "reference"):
                out["reference"] = await run_reference_sync(store_id)
            if scope in ("all", "transform"):
                out["transform"] = await run_transform()
            if scope in ("all", "ga4"):
                out["ga4"] = await run_ga4_sync()

            _sync_statuses[_sync_key(store_id)] = {
                "store_id": store_id,
                "scope": scope,
                "status": "done",
                "started_at": started_at,
                "finished_at": _now_iso(),
                "error": None,
                "result": out,
            }
            return out
        except Exception as exc:
            _sync_statuses[_sync_key(store_id)] = {
                "store_id": store_id,
                "scope": scope,
                "status": "error",
                "started_at": started_at,
                "finished_at": _now_iso(),
                "error": str(exc),
                "result": None,
            }
            raise


def setup_scheduler():
    scheduler.add_job(sync_all_stores_orders, "interval", hours=1, id="sync_orders")
    scheduler.add_job(sync_all_stores_products, "interval", hours=6, id="sync_products")
    scheduler.add_job(sync_all_stores_customers, "interval", hours=24, id="sync_customers")
    scheduler.add_job(sync_all_stores_reference, "interval", hours=24, id="sync_reference")
    scheduler.add_job(transform_core, "interval", hours=1, id="transform_core", misfire_grace_time=300)
    scheduler.add_job(sync_ga4_hourly, "interval", hours=1, id="sync_ga4", misfire_grace_time=1800)
    scheduler.start()
    logger.info("Scheduler started: orders/1h, products/6h, customers/24h, reference/24h, transform/1h, ga4/1h(today+yesterday)")
