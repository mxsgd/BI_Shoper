from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("store_id", "shoper_order_id", name="uq_orders_store_shoper"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    shoper_order_id: Mapped[int] = mapped_column(Integer, index=True)
    order_date: Mapped[str] = mapped_column(DateTime(timezone=True), index=True)
    status_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    shoper_customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="PLN")
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shipping_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    synced_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    shoper_product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_name: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_value: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    order: Mapped["Order"] = relationship(back_populates="items")
