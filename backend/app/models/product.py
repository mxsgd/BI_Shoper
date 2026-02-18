from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    shoper_product_id: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ean: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(500))
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    producer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    synced_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductSnapshot(Base):
    """Daily snapshot of product price/stock for trend analysis."""
    __tablename__ = "product_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    snapshot_date: Mapped[str] = mapped_column(Date, index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
