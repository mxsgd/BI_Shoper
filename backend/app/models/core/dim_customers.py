"""CORE: dim_customers - star schema dimension table."""
from sqlalchemy import BigInteger, String, Numeric, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class DimCustomer(Base):
    """Dimension table: customers with aggregated metrics. For LTV, RFM, retention analysis."""
    __tablename__ = "dim_customers"

    customer_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Dates
    first_order_date: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_order_date: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    
    # Aggregated metrics
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0, index=True)
    
    # Location (from most recent order or user address)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Segmentation
    customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # 'new' | 'returning'
    rfm_score: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)  # e.g., '555', '321'
    
    # Timestamp
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
