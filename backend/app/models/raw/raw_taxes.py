"""RAW: Tax rates from Shoper API."""
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawTax(Base):
    __tablename__ = "raw_taxes"
    __table_args__ = (
        UniqueConstraint("store_id", "tax_id", name="uq_raw_taxes_store_tax"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    tax_id: Mapped[int] = mapped_column(Integer, index=True)
    value: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tax_class: Mapped[str | None] = mapped_column(String(100), nullable=True)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
