"""RAW: Shipping methods from Shoper API - staging table."""
from sqlalchemy import BigInteger, String, Numeric, Integer, Boolean, JSON, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawShipping(Base):
    """Staging table for Shipping methods from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_shipments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Shoper API fields (1:1 mapping)
    shipping_id: Mapped[int] = mapped_column(Integer, index=True, unique=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_shipping: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    engine: Mapped[str | None] = mapped_column(String(100), nullable=True)  # personal, pickupPoint, apaczka, etc.
    
    # Nested objects stored as JSON
    translations: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Multi-lang: name, description
    ranges: Mapped[list | None] = mapped_column(JSON, nullable=True)  # Weight/price ranges
    payments: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Payment methods assigned
    countries: Mapped[list | None] = mapped_column(JSON, nullable=True)  # Supported countries
    
    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
