"""
Scheduled sync jobs using APScheduler.
Runs order sync hourly, products every 6h, customers daily.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..database import async_session
from ..models.store import Store
from ..services.sync_service import SyncService
from sqlalchemy import select

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def sync_all_stores_orders():
    """Sync orders for all active stores."""
    async with async_session() as db:
        stores = (await db.execute(select(Store).where(Store.is_active == True))).scalars().all()
        for store in stores:
            try:
                svc = SyncService(db, store)
                count = await svc.sync_orders(since=store.last_sync_orders)
                store.last_sync_orders = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                await db.commit()
                logger.info("Orders sync done for %s: %d", store.name, count)
                await svc.close()
            except Exception as e:
                logger.error("Orders sync failed for %s: %s", store.name, e)


async def sync_all_stores_products():
    """Sync products for all active stores."""
    async with async_session() as db:
        stores = (await db.execute(select(Store).where(Store.is_active == True))).scalars().all()
        for store in stores:
            try:
                svc = SyncService(db, store)
                count = await svc.sync_products()
                store.last_sync_products = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                await db.commit()
                logger.info("Products sync done for %s: %d", store.name, count)
                await svc.close()
            except Exception as e:
                logger.error("Products sync failed for %s: %s", store.name, e)


async def sync_all_stores_customers():
    """Sync customers for all active stores."""
    async with async_session() as db:
        stores = (await db.execute(select(Store).where(Store.is_active == True))).scalars().all()
        for store in stores:
            try:
                svc = SyncService(db, store)
                count = await svc.sync_customers()
                store.last_sync_customers = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                await db.commit()
                logger.info("Customers sync done for %s: %d", store.name, count)
                await svc.close()
            except Exception as e:
                logger.error("Customers sync failed for %s: %s", store.name, e)


def setup_scheduler():
    scheduler.add_job(sync_all_stores_orders, "interval", hours=1, id="sync_orders")
    scheduler.add_job(sync_all_stores_products, "interval", hours=6, id="sync_products")
    scheduler.add_job(sync_all_stores_customers, "interval", hours=24, id="sync_customers")
    scheduler.start()
    logger.info("Scheduler started: orders/1h, products/6h, customers/24h")
