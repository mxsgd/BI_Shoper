from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ..database import get_db
from ..models.order import Order

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/")
async def list_orders(
    store_id: int = Query(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page
    q = (
        select(Order)
        .where(Order.store_id == store_id)
        .order_by(Order.order_date.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(q)
    orders = result.scalars().all()

    count_q = select(func.count(Order.id)).where(Order.store_id == store_id)
    total = (await db.execute(count_q)).scalar() or 0

    return {
        "items": [_serialize(o) for o in orders],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


def _serialize(o: Order) -> dict:
    return {
        "id": o.id,
        "shoper_order_id": o.shoper_order_id,
        "order_date": str(o.order_date) if o.order_date else None,
        "status_name": o.status_name,
        "total": float(o.total),
        "currency": o.currency,
    }
