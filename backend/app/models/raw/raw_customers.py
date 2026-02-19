"""RAW: Users (customers) from Shoper API - staging table."""
from sqlalchemy import BigInteger, String, Numeric, Integer, Boolean, JSON, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawCustomer(Base):
    """Staging table for Users (customers) from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    
    # Shoper API fields (1:1 mapping)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    firstname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lastname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_add: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lastvisit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    discount: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=shop, 1=facebook, 2=mobile, 3=allegro
    
    # Nested objects stored as JSON
    additional_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
