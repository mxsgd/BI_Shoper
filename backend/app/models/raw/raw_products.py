"""RAW: Products from Shoper API - staging table."""
from sqlalchemy import BigInteger, String, Numeric, Integer, Boolean, JSON, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawProduct(Base):
    """Staging table for Products from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Shoper API fields (1:1 mapping)
    product_id: Mapped[int] = mapped_column(BigInteger, index=True, unique=True)
    type: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=product, 1=bundle
    producer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    category_tree_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tax_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    add_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    edit_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ean: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Nested objects stored as JSON
    stock: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Base stock info
    translations: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Multi-lang: name, description, etc.
    categories: Mapped[list | None] = mapped_column(JSON, nullable=True)  # Array of category IDs
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    special_offer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    children: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Bundle children
    
    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
