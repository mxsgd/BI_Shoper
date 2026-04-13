"""RAW: Product Stock (SKU/variant level) from Shoper API."""
from sqlalchemy import BigInteger, String, Integer, Numeric, Boolean, JSON, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawProductStock(Base):
    __tablename__ = "raw_product_stocks"
    __table_args__ = (
        UniqueConstraint("store_id", "stock_id", name="uq_raw_product_stocks_store_stock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    stock_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(BigInteger, index=True)
    extended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ean: Mapped[str | None] = mapped_column(String(50), nullable=True)

    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    price_wholesale: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_special: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_buying: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    stock: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    warn_level: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    sold: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    weight: Mapped[float] = mapped_column(Numeric(10, 3), default=0)

    availability_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    warehouses: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    special_offer: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
