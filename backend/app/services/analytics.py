"""
Analytics service: KPI calculations, trends, and aggregations.
"""

import logging
from datetime import date, timedelta, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from ..models.order import Order, OrderItem
from ..models.product import Product
from ..models.customer import Customer

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_kpis(
        self, store_id: int, period_days: int = 30
    ) -> dict:
        """Revenue, orders, AOV, new customers for given period."""
        since = datetime.utcnow() - timedelta(days=period_days)

        orders_q = select(
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total), 0).label("revenue"),
        ).where(
            and_(Order.store_id == store_id, Order.order_date >= since)
        )
        result = (await self.db.execute(orders_q)).one()
        order_count = result.order_count or 0
        revenue = float(result.revenue or 0)
        aov = revenue / order_count if order_count > 0 else 0

        new_customers_q = select(func.count(Customer.id)).where(
            and_(Customer.store_id == store_id, Customer.first_order_date >= since)
        )
        new_customers = (await self.db.execute(new_customers_q)).scalar() or 0

        return {
            "period_days": period_days,
            "revenue": round(revenue, 2),
            "orders": order_count,
            "aov": round(aov, 2),
            "new_customers": new_customers,
        }

    async def get_revenue_chart(
        self, store_id: int, period_days: int = 30
    ) -> list[dict]:
        """Daily revenue breakdown for chart."""
        since = datetime.utcnow() - timedelta(days=period_days)

        q = (
            select(
                func.date(Order.order_date).label("day"),
                func.count(Order.id).label("orders"),
                func.coalesce(func.sum(Order.total), 0).label("revenue"),
            )
            .where(and_(Order.store_id == store_id, Order.order_date >= since))
            .group_by(func.date(Order.order_date))
            .order_by(func.date(Order.order_date))
        )
        rows = (await self.db.execute(q)).all()
        return [
            {"date": str(r.day), "orders": r.orders, "revenue": float(r.revenue)}
            for r in rows
        ]

    async def get_bestsellers(
        self, store_id: int, limit: int = 20
    ) -> list[dict]:
        """Top products by quantity sold."""
        q = (
            select(
                OrderItem.product_code,
                OrderItem.product_name,
                func.sum(OrderItem.quantity).label("total_qty"),
                func.sum(OrderItem.price * OrderItem.quantity).label("total_revenue"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(Order.store_id == store_id)
            .group_by(OrderItem.product_code, OrderItem.product_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
        )
        rows = (await self.db.execute(q)).all()
        return [
            {
                "code": r.product_code,
                "name": r.product_name,
                "quantity": int(r.total_qty),
                "revenue": float(r.total_revenue),
            }
            for r in rows
        ]
