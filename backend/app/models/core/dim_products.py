"""CORE: dim_products - star schema dimension table."""
from sqlalchemy import BigInteger, String, Numeric, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class DimProduct(Base):
    """Dimension table: products with pricing. For product analysis, Pareto, margin analysis."""
    __tablename__ = "dim_products"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Product info
    product_name: Mapped[str] = mapped_column(String(500), index=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)  # FK to dim_categories
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)  # producer_name
    
    # Pricing (for margin calculation)
    cost_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # From stock.price_wholesale or metafield
    retail_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, index=True)  # From stock.price
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    # Timestamp
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
