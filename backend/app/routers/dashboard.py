from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.analytics import AnalyticsService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/kpis")
async def get_kpis(
    store_id: int = Query(...),
    period: int = Query(30, description="Number of days"),
    db: AsyncSession = Depends(get_db),
):
    svc = AnalyticsService(db)
    return await svc.get_dashboard_kpis(store_id, period)


@router.get("/revenue-chart")
async def revenue_chart(
    store_id: int = Query(...),
    period: int = Query(30),
    db: AsyncSession = Depends(get_db),
):
    svc = AnalyticsService(db)
    return await svc.get_revenue_chart(store_id, period)
