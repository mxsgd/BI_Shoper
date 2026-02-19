"""CORE: fact_orders - star schema fact table."""
from sqlalchemy import BigInteger, String, Numeric, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class FactOrder(Base):
    """Fact table: one order = one record. Optimized for analytical queries."""
    __tablename__ = "fact_orders"

    order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)  # FK to dim_customers
    
    # Dates
    order_date: Mapped[str] = mapped_column(DateTime(timezone=True), index=True)
    payment_date: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Statuses
    order_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # From Statuses
    payment_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Derived: is_paid, paid amount
    shipment_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # From order status or parcels
    
    # Financial values
    gross_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0, index=True)
    net_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    shipping_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    margin_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)  # Calculated: gross - cost
    
    # Metrics
    items_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Marketing
    source_channel: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # origin: shop/facebook/mobile/allegro/webapi
    campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)  # promo_code
    
    # Timestamps
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
