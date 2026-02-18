"""
Sync service: fetches data from Shoper API and upserts into PostgreSQL.
Supports full sync (first run) and incremental (since last_sync_date).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models.store import Store
from ..models.order import Order, OrderItem
from ..models.product import Product
from ..models.customer import Customer
from .shoper_client import ShoperClient

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self, db: AsyncSession, store: Store):
        self.db = db
        self.store = store
        self.client = ShoperClient(store.api_url, store.api_token)

    async def close(self):
        await self.client.close()

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    async def sync_orders(self, since: datetime | None = None) -> int:
        """Fetch orders from Shoper and upsert into DB. Returns count."""
        params = {}
        if since:
            params["filters"] = f'{{"date_add":{{"+gte":"{since.isoformat()}"}}}}'

        orders = await self.client.get_all("/orders", params=params)
        count = 0

        for o in orders:
            shoper_id = int(o.get("order_id", o.get("id", 0)))
            if not shoper_id:
                continue

            stmt = pg_insert(Order).values(
                store_id=self.store.id,
                shoper_order_id=shoper_id,
                order_date=o.get("date_add"),
                status_id=_int_or_none(o.get("status_id")),
                status_name=o.get("status_name"),
                shoper_customer_id=_int_or_none(o.get("user_id")),
                total=_float_or_zero(o.get("sum")),
                currency=o.get("currency_id", "PLN"),
                payment_method=o.get("payment_id"),
                shipping_method=o.get("shipping_id"),
            ).on_conflict_do_update(
                index_elements=["store_id", "shoper_order_id"],
                set_={
                    "status_id": _int_or_none(o.get("status_id")),
                    "status_name": o.get("status_name"),
                    "total": _float_or_zero(o.get("sum")),
                },
            )
            # NOTE: on_conflict requires a unique constraint on (store_id, shoper_order_id)
            # to be added in Alembic migration
            await self.db.execute(stmt)
            count += 1

        await self.db.commit()
        logger.info("Synced %d orders for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    async def sync_products(self) -> int:
        """Fetch all products and upsert."""
        products = await self.client.get_all("/products")
        count = 0

        for p in products:
            shoper_id = int(p.get("product_id", p.get("id", 0)))
            if not shoper_id:
                continue

            name = _extract_translation(p.get("translations", {}), "name")

            existing = await self.db.execute(
                select(Product).where(
                    Product.store_id == self.store.id,
                    Product.shoper_product_id == shoper_id,
                )
            )
            product = existing.scalar_one_or_none()
            if product:
                product.name = name or product.name
                product.code = p.get("code") or product.code
                product.price = _float_or_zero(p.get("price"))
                product.stock_quantity = _int_or_none(p.get("stock", {}).get("stock")) or 0
                product.synced_at = datetime.now(timezone.utc)
            else:
                product = Product(
                    store_id=self.store.id,
                    shoper_product_id=shoper_id,
                    code=p.get("code"),
                    ean=p.get("ean"),
                    name=name or f"Product #{shoper_id}",
                    price=_float_or_zero(p.get("price")),
                    stock_quantity=_int_or_none(p.get("stock", {}).get("stock")) or 0,
                )
                self.db.add(product)
            count += 1

        await self.db.commit()
        logger.info("Synced %d products for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------
    async def sync_customers(self) -> int:
        """Fetch all customers and upsert."""
        customers = await self.client.get_all("/customers")
        count = 0

        for c in customers:
            shoper_id = int(c.get("customer_id", c.get("id", 0)))
            if not shoper_id:
                continue

            existing = await self.db.execute(
                select(Customer).where(
                    Customer.store_id == self.store.id,
                    Customer.shoper_customer_id == shoper_id,
                )
            )
            customer = existing.scalar_one_or_none()
            if customer:
                customer.email = c.get("email") or customer.email
                customer.first_name = c.get("name") or customer.first_name
                customer.last_name = c.get("lastname") or customer.last_name
                customer.synced_at = datetime.now(timezone.utc)
            else:
                customer = Customer(
                    store_id=self.store.id,
                    shoper_customer_id=shoper_id,
                    email=c.get("email"),
                    first_name=c.get("name"),
                    last_name=c.get("lastname"),
                    city=c.get("city"),
                )
                self.db.add(customer)
            count += 1

        await self.db.commit()
        logger.info("Synced %d customers for store %s", count, self.store.name)
        return count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _int_or_none(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _float_or_zero(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _extract_translation(translations: dict, field: str, lang: str = "pl_PL") -> str | None:
    """Extract translated field from Shoper translations dict."""
    if not translations:
        return None
    t = translations.get(lang) or translations.get("en_GB") or {}
    if isinstance(t, dict):
        return t.get(field)
    return None
