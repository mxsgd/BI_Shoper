"""RAW: Payment methods from Shoper API - staging table."""
from sqlalchemy import String, Integer, JSON, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawPayment(Base):
    """Staging table for Payment methods from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Shoper API fields (1:1 mapping)
    payment_id: Mapped[int] = mapped_column(Integer, index=True, unique=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Engine name (e.g., "external")
    order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Nested objects stored as JSON
    translations: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Multi-lang: title, description
    currencies: Mapped[list | None] = mapped_column(JSON, nullable=True)  # Array of currency IDs
    
    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
