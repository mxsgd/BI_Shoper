"""
BI Shoper - Shoper Analytics Tool
FastAPI backend entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import engine, async_session
from .migrations import current_revision, ensure_schema_current
from .routers import dashboard, orders, products, customers, stores, analytics, price_update, variant_codes, shoper_app, settings
from .scheduler.jobs import setup_scheduler
from .services.transform_service import TransformService

# Import all models to register them with SQLAlchemy
from .models import (
    Store,
    ShoperAppInstallation,
    PriceUpdateJobRecord,
    PriceUpdateLogRecord,
    RawOrder, RawOrderItem, RawProduct, RawCustomer,
    RawPayment, RawShipping, RawCategory, RawDiscount, RawStatus,
    RawProducer, RawTax, RawProductStock, RawParcel, RawUserGroup, RawCurrency,
    RawGA4Traffic, RawGA4Source, RawGA4Page, RawGA4Geo, RawGA4Device,
    RawGA4Funnel, RawGA4FunnelDevice, RawGA4CartProduct,
    FactOrder, FactOrderItem,
    DimCustomer, DimProduct, DimCategory, DimDate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast on incomplete App Store configuration. The message lists
    # missing variable NAMES only - never their values.
    missing = get_settings().validate_shoper_appstore()
    if missing:
        raise RuntimeError(
            "Shoper App Store integration is enabled but required settings are "
            f"missing: {', '.join(missing)}"
        )
    dev_store = get_settings().dev_store_id
    if dev_store:
        logging.getLogger(__name__).warning(
            "DEV_STORE_ID=%s: requests from this machine without an app session act as store %s "
            "and may use admin endpoints. Development only - unset it on any deployed server.",
            dev_store, dev_store)
    # The schema belongs to Alembic (deploys run `alembic upgrade head` first); refuse to run on
    # anything older than the code expects.
    async with engine.connect() as conn:
        ensure_schema_current(await conn.run_sync(current_revision))
    async with async_session() as db:
        ts = TransformService(db)
        await ts.ensure_dim_date()
    from .services.price_update_persistence import fail_orphaned_jobs

    orphaned = await fail_orphaned_jobs()
    if orphaned:
        logging.getLogger(__name__).warning(
            "Marked %d orphaned price-update job(s) as FAILED on startup", orphaned
        )
    setup_scheduler()
    yield
    await engine.dispose()


app = FastAPI(
    title="BI Shoper",
    description="Business Intelligence for Shoper",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(orders.router)
app.include_router(products.router)
app.include_router(customers.router)
app.include_router(stores.router)
app.include_router(analytics.router)
app.include_router(price_update.router)
app.include_router(variant_codes.router)
app.include_router(shoper_app.router)
app.include_router(settings.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
