"""
Sync service: fetches data from Shoper API and upserts into PostgreSQL.
Supports full sync (first run) and incremental (since last_sync_date).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models.store import Store
from ..models.order import Order, OrderItem
from ..models.product import Product
from ..models.customer import Customer
from ..models.raw import (
    RawOrder, RawOrderItem, RawProduct, RawCustomer,
    RawPayment, RawShipping, RawCategory, RawProductGroup, RawDiscount, RawStatus,
    RawProducer, RawTax, RawProductStock, RawParcel, RawUserGroup, RawCurrency,
    RawSubscriber,
)
from .shoper_client import ShoperClient
from .shoper_auth import ensure_store_token

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self, db: AsyncSession, store: Store):
        self.db = db
        self.store = store
        self.client = ShoperClient(store.api_url, store.api_token, on_unauthorized=self._refresh_token)

    async def close(self):
        await self.client.close()

    async def _refresh_token(self) -> str:
        token = await ensure_store_token(self.db, self.store, force_refresh=True)
        self.client.set_token(token)
        return token

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    async def sync_orders(self, since: datetime | None = None) -> int:
        """Fetch orders from Shoper and upsert into DB. Returns count."""
        params = {}
        if since:
            # Shoper filtruje po polu "date" (data utworzenia), nie "date_add" — zły klucz dawał 404.
            # Format musi być "YYYY-MM-DD HH:MM:SS" (bez timezone/T) — Shoper nie rozumie ISO 8601 z offsetem.
            since_str = since.strftime("%Y-%m-%d %H:%M:%S")
            params["filters"] = f'{{"date":{{"+gte":"{since_str}"}}}}'

        orders = await self.client.get_all("/orders", params=params)
        count = 0

        for o in orders:
            shoper_id = int(o.get("order_id", o.get("id", 0)))
            if not shoper_id:
                continue

            order_dt = _parse_shoper_datetime(o.get("date") or o.get("date_add"))
            if order_dt is None:
                order_dt = datetime.now(timezone.utc)

            stmt = pg_insert(Order).values(
                store_id=self.store.id,
                shoper_order_id=shoper_id,
                order_date=order_dt,
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
            await self._upsert_raw_order(o)
            count += 1

        items_n = await self._replace_raw_order_items_for_store()
        await self.db.commit()
        logger.info(
            "Synced %d orders for store %s (raw_order_items rows: %d)",
            count,
            self.store.name,
            items_n,
        )
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
                select(Product)
                .where(
                    Product.store_id == self.store.id,
                    Product.shoper_product_id == shoper_id,
                )
                .limit(1)
            )
            product = existing.scalars().first()
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
            await self._upsert_raw_product(p)
            count += 1

        await self.db.commit()
        logger.info("Synced %d products for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------
    async def sync_customers(self) -> int:
        """Fetch registered users (Shoper REST: /users, not /customers)."""
        customers = await self.client.get_all("/users")
        count = 0

        for c in customers:
            shoper_id = int(c.get("user_id", c.get("customer_id", c.get("id", 0))))
            if not shoper_id:
                continue

            existing = await self.db.execute(
                select(Customer)
                .where(
                    Customer.store_id == self.store.id,
                    Customer.shoper_customer_id == shoper_id,
                )
                .limit(1)
            )
            customer = existing.scalars().first()
            fn = c.get("firstname") or c.get("name")
            ln = c.get("lastname")
            if customer:
                customer.email = c.get("email") or customer.email
                customer.first_name = fn or customer.first_name
                customer.last_name = ln or customer.last_name
                customer.synced_at = datetime.now(timezone.utc)
            else:
                customer = Customer(
                    store_id=self.store.id,
                    shoper_customer_id=shoper_id,
                    email=c.get("email"),
                    first_name=fn,
                    last_name=ln,
                    city=c.get("city"),
                )
                self.db.add(customer)
            await self._upsert_raw_customer(c)
            count += 1

        await self.db.commit()
        logger.info("Synced %d customers for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Payments (reference data)
    # ------------------------------------------------------------------
    async def sync_payments(self) -> int:
        """Fetch all payment methods and upsert into raw_payments."""
        items = await self.client.get_all("/payments")
        count = 0
        for p in items:
            row = _shoper_payment_to_raw_row(self.store.id, p)
            if not row:
                continue
            stmt = pg_insert(RawPayment).values(**row)
            exclude = {"store_id", "payment_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "payment_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d payments for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Shipments (reference data)
    # ------------------------------------------------------------------
    async def sync_shipments(self) -> int:
        """Fetch all shipping methods and upsert into raw_shipments."""
        items = await self.client.get_all("/shippings")
        count = 0
        for s in items:
            row = _shoper_shipping_to_raw_row(self.store.id, s)
            if not row:
                continue
            stmt = pg_insert(RawShipping).values(**row)
            exclude = {"store_id", "shipping_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "shipping_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d shipments for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Categories (reference data)
    # ------------------------------------------------------------------
    async def sync_categories(self) -> int:
        """Fetch all categories and upsert into raw_categories."""
        items = await self.client.get_all("/categories")
        count = 0
        for c in items:
            row = _shoper_category_to_raw_row(self.store.id, c)
            if not row:
                continue
            stmt = pg_insert(RawCategory).values(**row)
            exclude = {"store_id", "category_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "category_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d categories for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Product Groups / Zestawy wariantów (reference data)
    # ------------------------------------------------------------------
    async def sync_product_groups(self) -> int:
        """Fetch zestawy wariantów from /option-groups and upsert into raw_product_groups."""
        items = await self.client.get_all("/option-groups")
        count = 0
        for g in items:
            row = _shoper_product_group_to_raw_row(self.store.id, g)
            if not row:
                continue
            stmt = pg_insert(RawProductGroup).values(**row)
            exclude = {"store_id", "group_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "group_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d option-groups (zestawy wariantów) for store %s", count, self.store.name)
        return count

    async def sync_product_group_by_id(self, group_id: int) -> bool:
        """Fetch one zestaw wariantów from /option-groups/{id} and upsert metadata."""
        g = await self.client.get(f"/option-groups/{group_id}")
        if not g:
            items = await self.client.get_filtered("/option-groups", {"group_id": group_id})
            g = items[0] if items else None
        if not g:
            logger.warning("Option group %s not found in Shoper for store %s", group_id, self.store.name)
            return False
        row = _shoper_product_group_to_raw_row(self.store.id, g)
        if not row:
            return False
        stmt = pg_insert(RawProductGroup).values(**row)
        exclude = {"store_id", "group_id", "loaded_at"}
        set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
        set_["updated_at"] = datetime.now(timezone.utc)
        stmt = stmt.on_conflict_do_update(
            index_elements=["store_id", "group_id"], set_=set_
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return True

    async def sync_products_for_group(self, group_id: int) -> int:
        """Fetch products assigned to a product group and upsert into DB."""
        products = await self.client.get_filtered("/products", {"group_id": group_id})
        count = 0
        for p in products:
            shoper_id = int(p.get("product_id", p.get("id", 0)))
            if not shoper_id:
                continue

            name = _extract_translation(p.get("translations", {}), "name")

            existing = await self.db.execute(
                select(Product)
                .where(
                    Product.store_id == self.store.id,
                    Product.shoper_product_id == shoper_id,
                )
                .limit(1)
            )
            product = existing.scalars().first()
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
            await self._upsert_raw_product(p)
            count += 1

        await self.db.commit()
        logger.info(
            "Synced %d products for group %s (store %s)",
            count,
            group_id,
            self.store.name,
        )
        return count

    async def sync_product_stocks_for_group(self, group_id: int) -> int:
        """Fetch variant stocks for all products in a product group."""
        pids = (
            await self.db.execute(
                select(RawProduct.product_id).where(
                    RawProduct.store_id == self.store.id,
                    RawProduct.group_id == group_id,
                )
            )
        ).scalars().all()
        count = 0
        for pid in pids:
            stocks = await self.client.get_filtered("/product-stocks", {"product_id": pid})
            for s in stocks:
                row = _shoper_product_stock_to_raw_row(self.store.id, s)
                if not row:
                    continue
                stmt = pg_insert(RawProductStock).values(**row)
                exclude = {"store_id", "stock_id", "loaded_at"}
                set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
                set_["updated_at"] = datetime.now(timezone.utc)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["store_id", "stock_id"], set_=set_
                )
                await self.db.execute(stmt)
                count += 1
        await self.db.commit()
        logger.info(
            "Synced %d product stocks for group %s (store %s)",
            count,
            group_id,
            self.store.name,
        )
        return count

    async def sync_variant_group(self, group_id: int, *, include_stocks: bool = False) -> dict[str, int]:
        """Sync one zestaw wariantów: metadata + products. Stocks optional (slow)."""
        meta_ok = await self.sync_product_group_by_id(group_id)
        products = await self.sync_products_for_group(group_id)
        stocks = 0
        if include_stocks:
            stocks = await self.sync_product_stocks_for_group(group_id)
        return {
            "group_synced": int(meta_ok),
            "products": products,
            "stocks": stocks,
        }

    # ------------------------------------------------------------------
    # Statuses (reference data)
    # ------------------------------------------------------------------
    async def sync_statuses(self) -> int:
        """Fetch all order statuses and upsert into raw_statuses."""
        items = await self.client.get_all("/statuses")
        count = 0
        for s in items:
            row = _shoper_status_to_raw_row(self.store.id, s)
            if not row:
                continue
            stmt = pg_insert(RawStatus).values(**row)
            exclude = {"store_id", "status_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "status_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d statuses for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Producers (reference data)
    # ------------------------------------------------------------------
    async def sync_producers(self) -> int:
        items = await self.client.get_all("/producers")
        count = 0
        for p in items:
            row = _shoper_producer_to_raw_row(self.store.id, p)
            if not row:
                continue
            stmt = pg_insert(RawProducer).values(**row)
            exclude = {"store_id", "producer_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "producer_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d producers for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Taxes (reference data)
    # ------------------------------------------------------------------
    async def sync_taxes(self) -> int:
        items = await self.client.get_all("/taxes")
        count = 0
        for t in items:
            row = _shoper_tax_to_raw_row(self.store.id, t)
            if not row:
                continue
            stmt = pg_insert(RawTax).values(**row)
            exclude = {"store_id", "tax_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "tax_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d taxes for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Product Stocks (variant/SKU level)
    # ------------------------------------------------------------------
    async def sync_product_stocks(self) -> int:
        items = await self.client.get_all("/product-stocks")
        count = 0
        for s in items:
            row = _shoper_product_stock_to_raw_row(self.store.id, s)
            if not row:
                continue
            stmt = pg_insert(RawProductStock).values(**row)
            exclude = {"store_id", "stock_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "stock_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d product stocks for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Parcels (fulfillment tracking)
    # ------------------------------------------------------------------
    async def sync_parcels(self) -> int:
        items = await self.client.get_all("/parcels")
        count = 0
        for p in items:
            row = _shoper_parcel_to_raw_row(self.store.id, p)
            if not row:
                continue
            stmt = pg_insert(RawParcel).values(**row)
            exclude = {"store_id", "parcel_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "parcel_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d parcels for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # User Groups (reference data)
    # ------------------------------------------------------------------
    async def sync_user_groups(self) -> int:
        items = await self.client.get_all("/user-groups")
        count = 0
        for g in items:
            row = _shoper_user_group_to_raw_row(self.store.id, g)
            if not row:
                continue
            stmt = pg_insert(RawUserGroup).values(**row)
            exclude = {"store_id", "group_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "group_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d user groups for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Currencies (reference data)
    # ------------------------------------------------------------------
    async def sync_currencies(self) -> int:
        items = await self.client.get_all("/currencies")
        count = 0
        for c in items:
            row = _shoper_currency_to_raw_row(self.store.id, c)
            if not row:
                continue
            stmt = pg_insert(RawCurrency).values(**row)
            exclude = {"store_id", "currency_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "currency_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d currencies for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Subscribers (newsletter)
    # ------------------------------------------------------------------
    async def sync_subscribers(self) -> int:
        items = await self.client.get_all("/subscribers")
        count = 0
        for s in items:
            row = _shoper_subscriber_to_raw_row(self.store.id, s)
            if not row:
                continue
            stmt = pg_insert(RawSubscriber).values(**row)
            exclude = {"store_id", "subscriber_id", "loaded_at"}
            set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
            set_["updated_at"] = datetime.now(timezone.utc)
            stmt = stmt.on_conflict_do_update(
                index_elements=["store_id", "subscriber_id"], set_=set_
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        logger.info("Synced %d subscribers for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Categories Tree (hierarchy for dim_categories.parent_id)
    # ------------------------------------------------------------------
    async def sync_categories_tree(self) -> int:
        """Fetch /categories-tree and update parent_id in raw_categories."""
        tree = await self.client.get_all("/categories-tree")
        count = 0

        def _walk(nodes, parent_id=None):
            nonlocal count
            if isinstance(nodes, dict):
                nodes = list(nodes.values())
            for node in nodes:
                cat_id = node.get("id")
                if cat_id and parent_id is not None:
                    updates.append({"cat_id": int(cat_id), "parent_id": int(parent_id)})
                    count += 1
                children = node.get("__children")
                if children:
                    _walk(children, parent_id=cat_id)

        updates: list[dict] = []
        if isinstance(tree, list):
            for root in tree:
                cat_id = root.get("id")
                children = root.get("__children")
                if children:
                    _walk(children, parent_id=cat_id)
        elif isinstance(tree, dict):
            _walk(tree, parent_id=None)

        from sqlalchemy import text as sa_text
        for u in updates:
            await self.db.execute(
                sa_text(
                    "UPDATE raw_categories SET translations = "
                    "jsonb_set(COALESCE(translations, '{}')::jsonb, '{_parent_id}', :pid::text::jsonb) "
                    "WHERE store_id = :sid AND category_id = :cid"
                ),
                {"pid": str(u["parent_id"]), "sid": self.store.id, "cid": u["cat_id"]},
            )
        await self.db.commit()
        logger.info("Updated %d category parent links for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # Discounts (promotion codes + special offers)
    # ------------------------------------------------------------------
    async def sync_discounts(self) -> int:
        """Fetch promotion codes and special offers, insert into raw_discounts."""
        await self.db.execute(
            delete(RawDiscount).where(RawDiscount.store_id == self.store.id)
        )
        count = 0

        promos = await self.client.get_all("/promotion-codes")
        for p in promos:
            row = _shoper_promo_code_to_raw_row(self.store.id, p)
            if row:
                self.db.add(RawDiscount(**row))
                count += 1

        # Some stores (e.g. franchise variants) may not have the module enabled.
        specials = await self.client.get_all("/special-offers")
        for s in specials:
            row = _shoper_special_offer_to_raw_row(self.store.id, s)
            if row:
                self.db.add(RawDiscount(**row))
                count += 1

        await self.db.commit()
        logger.info("Synced %d discounts for store %s", count, self.store.name)
        return count

    # ------------------------------------------------------------------
    # RAW upsert helpers (private)
    # ------------------------------------------------------------------
    async def _upsert_raw_order(self, o: dict) -> None:
        row = _shoper_order_to_raw_row(self.store.id, o)
        if not row:
            return
        stmt = pg_insert(RawOrder).values(**row)
        exclude = {"store_id", "order_id", "loaded_at"}
        set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
        set_["updated_at"] = datetime.now(timezone.utc)
        stmt = stmt.on_conflict_do_update(
            index_elements=["store_id", "order_id"], set_=set_
        )
        await self.db.execute(stmt)

    async def _replace_raw_order_items_for_store(self) -> int:
        res = await self.db.execute(
            select(RawOrder.order_id).where(RawOrder.store_id == self.store.id)
        )
        order_ids = {int(r[0]) for r in res.fetchall()}
        if not order_ids:
            await self.db.execute(
                delete(RawOrderItem).where(RawOrderItem.store_id == self.store.id)
            )
            return 0

        lines = await self.client.get_all("/order-products")
        filtered = [
            ln
            for ln in lines
            if _int_or_none(ln.get("order_id")) in order_ids
        ]
        await self.db.execute(
            delete(RawOrderItem).where(RawOrderItem.store_id == self.store.id)
        )
        for ln in filtered:
            row = _shoper_order_line_to_raw_row(self.store.id, ln)
            if row:
                self.db.add(RawOrderItem(**row))
        return len(filtered)

    async def _upsert_raw_product(self, p: dict) -> None:
        row = _shoper_product_to_raw_row(self.store.id, p)
        if not row:
            return
        stmt = pg_insert(RawProduct).values(**row)
        exclude = {"store_id", "product_id", "loaded_at"}
        set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
        set_["updated_at"] = datetime.now(timezone.utc)
        stmt = stmt.on_conflict_do_update(
            index_elements=["store_id", "product_id"], set_=set_
        )
        await self.db.execute(stmt)

    async def _upsert_raw_customer(self, c: dict) -> None:
        row = _shoper_customer_to_raw_row(self.store.id, c)
        if not row:
            return
        stmt = pg_insert(RawCustomer).values(**row)
        exclude = {"store_id", "user_id", "loaded_at"}
        set_ = {k: getattr(stmt.excluded, k) for k in row if k not in exclude}
        set_["updated_at"] = datetime.now(timezone.utc)
        stmt = stmt.on_conflict_do_update(
            index_elements=["store_id", "user_id"], set_=set_
        )
        await self.db.execute(stmt)


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


def _parse_shoper_datetime(val) -> datetime | None:
    """API zwraca daty jako string; asyncpg wymaga datetime z strefą."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _bool_from_shoper(val) -> bool | None:
    """Shoper czasem zwraca active jako '1' / '0' zamiast bool."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(int(val))
    t = str(val).strip().lower()
    if t in ("1", "true", "yes", "on"):
        return True
    if t in ("0", "false", "no", "off", ""):
        return False
    return None


def _extract_translation(translations: dict, field: str, lang: str = "pl_PL") -> str | None:
    """Extract translated field from Shoper translations dict."""
    if not translations:
        return None
    t = translations.get(lang) or translations.get("en_GB") or {}
    if isinstance(t, dict):
        return t.get(field)
    return None


def _json_safe(val):
    if val is None or isinstance(val, (dict, list, str, int, float, bool)):
        return val
    return None


def _shoper_order_to_raw_row(store_id: int, o: dict) -> dict | None:
    oid = _int_or_none(o.get("order_id", o.get("id")))
    if not oid:
        return None
    date_val = o.get("date") or o.get("date_add") or ""
    return {
        "store_id": store_id,
        "order_id": oid,
        "user_id": _int_or_none(o.get("user_id")),
        "date": str(date_val) if date_val is not None else "",
        "status_date": o.get("status_date"),
        "confirm_date": o.get("confirm_date"),
        "delivery_date": o.get("delivery_date"),
        "status_id": _int_or_none(o.get("status_id")),
        "sum": _float_or_zero(o.get("sum")),
        "payment_id": _int_or_none(o.get("payment_id")),
        "shipping_id": _int_or_none(o.get("shipping_id")),
        "shipping_cost": _float_or_zero(o.get("shipping_cost")),
        "email": o.get("email"),
        "code": o.get("code"),
        "confirm": _bool_from_shoper(o.get("confirm")),
        "currency_id": _int_or_none(o.get("currency_id")),
        "currency_rate": None
        if o.get("currency_rate") is None
        else _float_or_zero(o.get("currency_rate")),
        "paid": _float_or_zero(o.get("paid")),
        "discount_client": _float_or_zero(o.get("discount_client")),
        "discount_group": _float_or_zero(o.get("discount_group")),
        "discount_levels": _float_or_zero(o.get("discount_levels")),
        "discount_code": _float_or_zero(o.get("discount_code")),
        "promo_code": o.get("promo_code"),
        "is_paid": _bool_from_shoper(o.get("is_paid")),
        "total_products": _int_or_none(o.get("total_products")),
        "origin": _int_or_none(o.get("origin")),
        "status": _json_safe(o.get("status")),
        "billing_address": _json_safe(o.get("billing_address")),
        "delivery_address": _json_safe(o.get("delivery_address")),
    }


def _shoper_order_line_to_raw_row(store_id: int, ln: dict) -> dict | None:
    order_id = _int_or_none(ln.get("order_id"))
    line_id = _int_or_none(ln.get("id"))
    if not order_id or not line_id:
        return None
    return {
        "store_id": store_id,
        "order_id": order_id,
        "order_item_id": line_id,
        "product_id": _int_or_none(ln.get("product_id")),
        "stock_id": _int_or_none(ln.get("stock_id")),
        "price": _float_or_zero(ln.get("price")),
        "discount_perc": _float_or_zero(ln.get("discount_perc")),
        "quantity": _float_or_zero(ln.get("quantity")),
        "name": ln.get("name"),
        "code": ln.get("code"),
        "tax": ln.get("tax"),
        "tax_value": _float_or_zero(ln.get("tax_value")),
        "unit": ln.get("unit"),
    }


def _shoper_product_to_raw_row(store_id: int, p: dict) -> dict | None:
    pid = _int_or_none(p.get("product_id", p.get("id")))
    if not pid:
        return None
    cats = p.get("categories")
    if isinstance(cats, tuple):
        cats = list(cats)
    elif cats is not None and not isinstance(cats, list):
        cats = None
    return {
        "store_id": store_id,
        "product_id": pid,
        "type": _int_or_none(p.get("type")),
        "producer_id": _int_or_none(p.get("producer_id")),
        "group_id": _int_or_none(p.get("group_id")),
        "category_id": _int_or_none(p.get("category_id")),
        "category_tree_id": _int_or_none(p.get("category_tree_id")),
        "tax_id": _int_or_none(p.get("tax_id")),
        "add_date": p.get("add_date"),
        "edit_date": p.get("edit_date"),
        "code": p.get("code"),
        "ean": p.get("ean"),
        "currency_id": _int_or_none(p.get("currency_id")),
        "stock": _json_safe(p.get("stock")),
        "translations": _json_safe(p.get("translations")),
        "categories": cats,
    }


def _shoper_customer_to_raw_row(store_id: int, c: dict) -> dict | None:
    uid = _int_or_none(c.get("user_id", c.get("customer_id", c.get("id"))))
    if not uid:
        return None
    first = c.get("firstname") or c.get("name")
    last = c.get("lastname")
    return {
        "store_id": store_id,
        "user_id": uid,
        "email": c.get("email"),
        "firstname": first,
        "lastname": last,
        "date_add": c.get("date_add"),
        "lastvisit": c.get("lastvisit"),
        "discount": _float_or_zero(c.get("discount")),
        "active": _bool_from_shoper(c.get("active")),
        "group_id": _int_or_none(c.get("group_id")),
        "origin": _int_or_none(c.get("origin")),
    }


def _shoper_payment_to_raw_row(store_id: int, p: dict) -> dict | None:
    pid = _int_or_none(p.get("payment_id", p.get("id")))
    if not pid:
        return None
    return {
        "store_id": store_id,
        "payment_id": pid,
        "name": p.get("name"),
        "order": _int_or_none(p.get("order")),
        "translations": _json_safe(p.get("translations")),
    }


def _shoper_shipping_to_raw_row(store_id: int, s: dict) -> dict | None:
    sid = _int_or_none(s.get("shipping_id", s.get("id")))
    if not sid:
        return None
    return {
        "store_id": store_id,
        "shipping_id": sid,
        "name": s.get("name"),
        "cost": _float_or_zero(s.get("cost")),
        "tax_id": _int_or_none(s.get("tax_id")),
        "free_shipping": _float_or_zero(s.get("free_shipping")) if s.get("free_shipping") is not None else None,
        "active": _bool_from_shoper(s.get("active")),
        "engine": s.get("engine"),
        "translations": _json_safe(s.get("translations")),
    }


def _shoper_category_to_raw_row(store_id: int, c: dict) -> dict | None:
    cid = _int_or_none(c.get("category_id", c.get("id")))
    if not cid:
        return None
    return {
        "store_id": store_id,
        "category_id": cid,
        "root": _bool_from_shoper(c.get("root")),
        "order": _int_or_none(c.get("order")),
        "translations": _json_safe(c.get("translations")),
    }


def _shoper_product_group_to_raw_row(store_id: int, g: dict) -> dict | None:
    gid = _int_or_none(g.get("group_id", g.get("id")))
    if not gid:
        return None
    name = _extract_translation(g.get("translations"), "name") or g.get("name") or ""
    return {
        "store_id": store_id,
        "group_id": gid,
        "name": str(name)[:255] if name else None,
        "translations": _json_safe(g.get("translations")),
    }


def _shoper_status_to_raw_row(store_id: int, s: dict) -> dict | None:
    sid = _int_or_none(s.get("status_id", s.get("id")))
    if not sid:
        return None
    name = _extract_translation(s.get("translations"), "name") or s.get("name")
    return {
        "store_id": store_id,
        "status_id": sid,
        "name": name,
        "type": _int_or_none(s.get("type")),
        "translations": _json_safe(s.get("translations")),
    }


def _shoper_promo_code_to_raw_row(store_id: int, p: dict) -> dict | None:
    pid = _int_or_none(p.get("promo_code_id", p.get("id")))
    if not pid:
        return None
    return {
        "store_id": store_id,
        "discount_type": "promotion_code",
        "promo_code_id": pid,
        "name": p.get("name"),
        "code": p.get("code"),
        "discount_type_code": _int_or_none(p.get("discount_type")),
        "discount": _float_or_zero(p.get("discount")) if p.get("discount") is not None else None,
        "max_discount_amount": _float_or_zero(p.get("max_discount_amount"))
        if p.get("max_discount_amount") is not None
        else None,
        "time_from": p.get("time_from"),
        "time_to": p.get("time_to"),
        "min_amount": _float_or_zero(p.get("min_amount")) if p.get("min_amount") is not None else None,
        "usage_limit": _int_or_none(p.get("usage_limit")),
        "peruser_limit": _int_or_none(p.get("peruser_limit")),
        "usage_count": _int_or_none(p.get("usage_count")),
        "active": _int_or_none(p.get("active")),
    }


def _shoper_special_offer_to_raw_row(store_id: int, s: dict) -> dict | None:
    pid = _int_or_none(s.get("promo_id", s.get("id")))
    product_id = _int_or_none(s.get("product_id"))
    if not pid and not product_id:
        return None
    return {
        "store_id": store_id,
        "discount_type": "special_offer",
        "promo_id": pid,
        "product_id": product_id,
        "stock_id": _int_or_none(s.get("stock_id")),
        "discount": _float_or_zero(s.get("discount")) if s.get("discount") is not None else None,
        "discount_type_code": _int_or_none(s.get("discount_type")),
        "date_from": s.get("date_from"),
        "date_to": s.get("date_to"),
        "discount_wholesale": _float_or_zero(s.get("discount_wholesale")) if s.get("discount_wholesale") is not None else None,
        "discount_special": _float_or_zero(s.get("discount_special")) if s.get("discount_special") is not None else None,
        "condition_type": _int_or_none(s.get("condition_type")),
        "stocks": _json_safe(s.get("stocks")),
    }


def _shoper_producer_to_raw_row(store_id: int, p: dict) -> dict | None:
    pid = _int_or_none(p.get("producer_id", p.get("id")))
    if not pid:
        return None
    return {
        "store_id": store_id,
        "producer_id": pid,
        "name": p.get("name"),
        "web": p.get("web"),
        "isdefault": _bool_from_shoper(p.get("isdefault")),
        "translations": _json_safe(p.get("translations")),
    }


def _shoper_tax_to_raw_row(store_id: int, t: dict) -> dict | None:
    tid = _int_or_none(t.get("tax_id", t.get("id")))
    if not tid:
        return None
    return {
        "store_id": store_id,
        "tax_id": tid,
        "value": _float_or_zero(t.get("value")),
        "name": t.get("name"),
        "tax_class": t.get("class"),
    }


def _shoper_product_stock_to_raw_row(store_id: int, s: dict) -> dict | None:
    sid = _int_or_none(s.get("stock_id", s.get("id")))
    pid = _int_or_none(s.get("product_id"))
    if not sid or not pid:
        return None
    opts = s.get("options")
    if isinstance(opts, tuple):
        opts = list(opts)
    elif opts is not None and not isinstance(opts, list):
        opts = None
    return {
        "store_id": store_id,
        "stock_id": sid,
        "product_id": pid,
        "extended": _bool_from_shoper(s.get("extended")),
        "active": _bool_from_shoper(s.get("active")),
        "default": _bool_from_shoper(s.get("default")),
        "code": s.get("code"),
        "ean": s.get("ean"),
        "price": _float_or_zero(s.get("price")),
        "price_wholesale": _float_or_zero(s.get("price_wholesale")) if s.get("price_wholesale") is not None else None,
        "price_special": _float_or_zero(s.get("price_special")) if s.get("price_special") is not None else None,
        "price_buying": _float_or_zero(s.get("price_buying")) if s.get("price_buying") is not None else None,
        "stock": _float_or_zero(s.get("stock")),
        "warn_level": _float_or_zero(s.get("warn_level")) if s.get("warn_level") is not None else None,
        "sold": _float_or_zero(s.get("sold")),
        "weight": _float_or_zero(s.get("weight")),
        "availability_id": _int_or_none(s.get("availability_id")),
        "delivery_id": _int_or_none(s.get("delivery_id")),
        "warehouses": _json_safe(s.get("warehouses")),
        "options": opts,
        "special_offer": _json_safe(s.get("special_offer")),
    }


def _shoper_parcel_to_raw_row(store_id: int, p: dict) -> dict | None:
    pid = _int_or_none(p.get("parcel_id", p.get("id")))
    if not pid:
        return None
    prods = p.get("products")
    if isinstance(prods, dict):
        prods = list(prods.values())
    return {
        "store_id": store_id,
        "parcel_id": pid,
        "order_id": _int_or_none(p.get("order_id")) or 0,
        "shipping_id": _int_or_none(p.get("shipping_id")),
        "shipping_code": p.get("shipping_code"),
        "weight": _float_or_zero(p.get("weight")),
        "send_date": p.get("send_date"),
        "delivery_date": p.get("delivery_date"),
        "order_date": p.get("order_date"),
        "insurance": _bool_from_shoper(p.get("insurance")),
        "insurance_cost": _float_or_zero(p.get("insurance_cost")),
        "cod": _bool_from_shoper(p.get("cod")),
        "cod_cost": _float_or_zero(p.get("cod_cost")),
        "sent": _bool_from_shoper(p.get("sent")),
        "warehouse_id": _int_or_none(p.get("warehouse_id")),
        "delivery_address": _json_safe(p.get("delivery_address")),
        "products": prods if isinstance(prods, list) else None,
    }


def _shoper_user_group_to_raw_row(store_id: int, g: dict) -> dict | None:
    gid = _int_or_none(g.get("group_id", g.get("id")))
    if not gid:
        return None
    return {
        "store_id": store_id,
        "group_id": gid,
        "name": g.get("name"),
        "discount": _float_or_zero(g.get("discount")),
        "price_level": _int_or_none(g.get("price_level")),
        "auto_add": _bool_from_shoper(g.get("auto_add")),
    }


def _shoper_currency_to_raw_row(store_id: int, c: dict) -> dict | None:
    cid = _int_or_none(c.get("currency_id", c.get("id")))
    if not cid:
        return None
    return {
        "store_id": store_id,
        "currency_id": cid,
        "name": c.get("name"),
        "rate": _float_or_zero(c.get("rate")) or 1,
        "active": _bool_from_shoper(c.get("active")),
        "is_default": _bool_from_shoper(c.get("default")),
        "rate_sync": _float_or_zero(c.get("rate_sync")) if c.get("rate_sync") is not None else None,
        "rate_date": c.get("rate_date"),
    }


def _shoper_subscriber_to_raw_row(store_id: int, s: dict) -> dict | None:
    sid = _int_or_none(s.get("subscriber_id", s.get("id")))
    if not sid:
        return None
    return {
        "store_id": store_id,
        "subscriber_id": sid,
        "email": s.get("email"),
        "active": _bool_from_shoper(s.get("active")),
        "dateadd": s.get("dateadd"),
        "ipaddress": s.get("ipaddress"),
        "lang_id": _int_or_none(s.get("lang_id")),
    }
