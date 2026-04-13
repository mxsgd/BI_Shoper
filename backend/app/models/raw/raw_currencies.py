"""RAW: Currencies from Shoper API."""
from sqlalchemy import String, Integer, Numeric, Boolean, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawCurrency(Base):
    __tablename__ = "raw_currencies"
    __table_args__ = (
        UniqueConstraint("store_id", "currency_id", name="uq_raw_currencies_store_currency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    currency_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rate: Mapped[float] = mapped_column(Numeric(12, 6), default=1)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rate_sync: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    rate_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
