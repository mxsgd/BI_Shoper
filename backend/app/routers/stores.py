from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.store import Store

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


@router.delete("/{store_id}")
async def delete_store(store_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(404, "Store not found")
    await db.delete(store)
    await db.commit()
    return {"deleted": True}
