"""RAW: Categories from Shoper API - staging table."""
from sqlalchemy import BigInteger, String, Boolean, Integer, JSON, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawCategory(Base):
    """Staging table for Categories from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_categories"
    __table_args__ = (
        UniqueConstraint("store_id", "category_id", name="uq_raw_categories_store_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Shoper API fields (1:1 mapping)
    category_id: Mapped[int] = mapped_column(BigInteger, index=True)
    root: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Nested objects stored as JSON
    translations: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Multi-lang: name, description, seo_url, etc.
    
    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
