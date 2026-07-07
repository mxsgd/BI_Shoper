"""
BI Shoper - Shoper Analytics Tool
FastAPI backend entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, Base, async_session
from .routers import dashboard, orders, products, customers, stores, analytics, price_update, variant_codes
from .scheduler.jobs import setup_scheduler
from .services.transform_service import TransformService

# Import all models to register them with SQLAlchemy
from .models import (
    Store,
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


async def _ensure_constraints(conn):
    """Add unique constraints that create_all can't add to existing tables."""
    from sqlalchemy import text as sa_text

    old_indexes = [
        "ix_raw_orders_order_id",
        "ix_raw_products_product_id",
        "ix_raw_customers_user_id",
        "ix_raw_payments_payment_id",
        "ix_raw_shipments_shipping_id",
        "ix_raw_categories_category_id",
        "raw_orders_order_id_key",
        "raw_products_product_id_key",
        "raw_customers_user_id_key",
        "raw_payments_payment_id_key",
        "raw_shipments_shipping_id_key",
        "raw_categories_category_id_key",
    ]
    for idx in old_indexes:
        try:
            await conn.execute(sa_text(f"DROP INDEX IF EXISTS {idx}"))
        except Exception:
            pass
        try:
            await conn.execute(sa_text(
                f"ALTER TABLE IF EXISTS raw_orders DROP CONSTRAINT IF EXISTS {idx}"
            ))
        except Exception:
            pass

    constraints = [
        ("uq_orders_store_shoper",
         "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_store_shoper ON orders (store_id, shoper_order_id)"),
        ("uq_raw_orders_store_order",
         "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_orders_store_order ON raw_orders (store_id, order_id)"),
        ("uq_raw_products_store_product",
         "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_products_store_product ON raw_products (store_id, product_id)"),
        ("uq_raw_customers_store_user",
         "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_customers_store_user ON raw_customers (store_id, user_id)"),
        ("uq_raw_payments_store_payment",
         "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_payments_store_payment ON raw_payments (store_id, payment_id)"),
        ("uq_raw_shipments_store_shipping",
         "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_shipments_store_shipping ON raw_shipments (store_id, shipping_id)"),
        ("uq_raw_categories_store_category",
         "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_categories_store_category ON raw_categories (store_id, category_id)"),
    ]
    for name, ddl in constraints:
        try:
            await conn.execute(sa_text(ddl))
        except Exception:
            pass

    alter_cols = [
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS api_login VARCHAR(255)",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS api_password VARCHAR(255)",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS api_token_expires_at TIMESTAMPTZ",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS api_token_updated_at TIMESTAMPTZ",
        "ALTER TABLE stores ALTER COLUMN api_token SET DEFAULT ''",
        "ALTER TABLE raw_ga4_funnel ADD COLUMN IF NOT EXISTS remove_from_cart INTEGER DEFAULT 0",
        "ALTER TABLE raw_ga4_funnel ADD COLUMN IF NOT EXISTS add_to_cart_value NUMERIC(12,2) DEFAULT 0",
        "ALTER TABLE raw_ga4_funnel ADD COLUMN IF NOT EXISTS purchase_value NUMERIC(12,2) DEFAULT 0",
        # Product group support
        "ALTER TABLE raw_products ADD COLUMN IF NOT EXISTS group_id BIGINT",
    ]
    for ddl in alter_cols:
        try:
            await conn.execute(sa_text(ddl))
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import text as sa_text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_constraints(conn)
    # CREATE INDEX CONCURRENTLY must run outside a transaction block
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            await conn.execute(sa_text(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_raw_products_group_id ON raw_products (group_id)"
            ))
        except Exception:
            pass
    async with async_session() as db:
        ts = TransformService(db)
        await ts.ensure_dim_date()
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
