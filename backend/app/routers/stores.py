from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.store import Store
from ..scheduler.jobs import run_sync_now

router = APIRouter(prefix="/api/stores", tags=["stores"])


class StoreCreate(BaseModel):
    name: str
    api_url: str
    api_token: str


class StoreOut(BaseModel):
    id: int
    name: str
    api_url: str
    is_active: bool
    last_sync_orders: str | None = None
    last_sync_products: str | None = None


class SyncNowBody(BaseModel):
    """Trigger the same sync logic as the background scheduler."""

    store_id: int | None = None
    scope: Literal["all", "orders", "products", "customers", "reference", "transform"] = "all"


@router.get("/")
async def list_stores(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store).order_by(Store.name))
    stores = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "api_url": s.api_url,
            "is_active": s.is_active,
            "last_sync_orders": str(s.last_sync_orders) if s.last_sync_orders else None,
            "last_sync_products": str(s.last_sync_products) if s.last_sync_products else None,
        }
        for s in stores
    ]


@router.post("/")
async def create_store(body: StoreCreate, db: AsyncSession = Depends(get_db)):
    store = Store(name=body.name, api_url=body.api_url, api_token=body.api_token)
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return {"id": store.id, "name": store.name}


@router.post("/sync-now")
async def sync_now(
    body: SyncNowBody = SyncNowBody(),
    db: AsyncSession = Depends(get_db),
):
    """
    Run sync immediately for all active stores, or one store if `store_id` is set.
    `scope`: `all` (orders + products + customers), or a single phase.
    """
    if body.store_id is not None:
        res = await db.execute(select(Store).where(Store.id == body.store_id))
        store = res.scalar_one_or_none()
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")
        if not store.is_active:
            raise HTTPException(status_code=400, detail="Store is inactive")

    return await run_sync_now(store_id=body.store_id, scope=body.scope)


@router.delete("/{store_id}")
async def delete_store(store_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(404, "Store not found")
    await db.delete(store)
    await db.commit()
    return {"deleted": True}
