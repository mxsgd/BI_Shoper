from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..models.product import Product
from ..services.analytics import AnalyticsService

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/")
async def list_products(
    store_id: int = Query(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page
    q = (
        select(Product)
        .where(Product.store_id == store_id)
        .order_by(Product.name)
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(q)
    products = result.scalars().all()

    count_q = select(func.count(Product.id)).where(Product.store_id == store_id)
    total = (await db.execute(count_q)).scalar() or 0

    return {
        "items": [_serialize(p) for p in products],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/bestsellers")
async def bestsellers(
    store_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    svc = AnalyticsService(db)
    return await svc.get_bestsellers(store_id, limit)


def _serialize(p: Product) -> dict:
    return {
        "id": p.id,
        "shoper_product_id": p.shoper_product_id,
        "code": p.code,
        "name": p.name,
        "price": float(p.price),
        "stock": p.stock_quantity,
        "category": p.category_name,
    }
