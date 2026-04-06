"""RAW: Order Products from Shoper API - staging table."""
from sqlalchemy import BigInteger, String, Numeric, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawOrderItem(Base):
    """Staging table for Order Products from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    order_id: Mapped[int] = mapped_column(BigInteger, index=True)  # References raw_orders.order_id
    
    # Shoper API fields (1:1 mapping)
    order_item_id: Mapped[int] = mapped_column(BigInteger, index=True)  # API field: id
    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    stock_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_perc: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tax: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tax_value: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
