"""
BI Shoper - Shoper Analytics Tool
FastAPI backend entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, Base
from .routers import dashboard, orders, products, customers, stores
from .scheduler.jobs import setup_scheduler

# Import all models to register them with SQLAlchemy
from .models import (
    Store,
    RawOrder, RawOrderItem, RawProduct, RawCustomer,
    RawPayment, RawShipping, RawCategory, RawDiscount,
    FactOrder, FactOrderItem,
    DimCustomer, DimProduct, DimCategory, DimDate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    setup_scheduler()
    yield
    await engine.dispose()


app = FastAPI(
    title="BI Shoper",
    description="Analiza biznesowa sklepow Shoper",
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
