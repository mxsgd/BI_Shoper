from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..database import get_db
from ..models.customer import Customer

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("/")
async def list_customers(
    store_id: int = Query(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page
    q = (
        select(Customer)
        .where(Customer.store_id == store_id)
        .order_by(Customer.total_spent.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(q)
    customers = result.scalars().all()

    count_q = select(func.count(Customer.id)).where(Customer.store_id == store_id)
    total = (await db.execute(count_q)).scalar() or 0

    return {
        "items": [_serialize(c) for c in customers],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


def _serialize(c: Customer) -> dict:
    return {
        "id": c.id,
        "email": c.email,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "orders_count": c.orders_count,
        "total_spent": float(c.total_spent),
        "last_order_date": str(c.last_order_date) if c.last_order_date else None,
    }
