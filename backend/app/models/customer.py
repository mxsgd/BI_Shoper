from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    shoper_customer_id: Mapped[int] = mapped_column(Integer, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    orders_count: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    first_order_date: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_order_date: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
