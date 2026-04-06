"""RAW: Promotion codes and Special offers from Shoper API - staging table."""
from sqlalchemy import BigInteger, String, Numeric, Integer, JSON, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawDiscount(Base):
    """Staging table for Promotion codes and Special offers from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_discounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Type discriminator: 'promotion_code' or 'special_offer'
    discount_type: Mapped[str] = mapped_column(String(50), index=True)  # 'promotion_code' | 'special_offer'
    
    # Promotion codes fields
    promo_code_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)  # For promotion codes
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    discount_type_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_discount_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    time_from: Mapped[str | None] = mapped_column(String(50), nullable=True)
    time_to: Mapped[str | None] = mapped_column(String(50), nullable=True)
    min_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peruser_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Special offers fields
    promo_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)  # For special offers
    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    stock_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    date_from: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_to: Mapped[str | None] = mapped_column(String(50), nullable=True)
    discount_wholesale: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_special: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    condition_type: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Nested objects stored as JSON (Special offers: stocks per ShoperAPI-Reference.md)
    stocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
