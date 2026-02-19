"""CORE: fact_order_items - star schema fact table."""
from sqlalchemy import BigInteger, Numeric, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class FactOrderItem(Base):
    """Fact table: one product in order = one record. Optimized for analytical queries."""
    __tablename__ = "fact_order_items"

    order_item_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fact_orders.order_id"), index=True)
    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)  # FK to dim_products
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)  # FK to dim_categories
    
    # Quantities and prices
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_price_gross: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    unit_price_net: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_gross: Mapped[float] = mapped_column(Numeric(12, 2), default=0, index=True)
    total_net: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    
    # Denormalized date for time-based analysis
    order_date: Mapped[str] = mapped_column(DateTime(timezone=True), index=True)
