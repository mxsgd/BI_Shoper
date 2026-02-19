"""RAW: Orders from Shoper API - staging table."""
from sqlalchemy import BigInteger, String, Numeric, DateTime, Integer, Boolean, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawOrder(Base):
    """Staging table for Orders from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Shoper API fields (1:1 mapping)
    order_id: Mapped[int] = mapped_column(BigInteger, index=True, unique=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    date: Mapped[str] = mapped_column(String(50))  # ISO format from API
    status_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confirm_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sum: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confirm: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_rate: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_client: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    discount_group: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    discount_levels: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    discount_code: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    promo_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_paid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    total_products: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=shop, 1=facebook, 2=mobile, 3=allegro, 4=webapi
    
    # Nested objects stored as JSON
    status: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    billing_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    delivery_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    additional_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
