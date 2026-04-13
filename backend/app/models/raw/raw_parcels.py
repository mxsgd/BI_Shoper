"""RAW: Parcels (shipment tracking) from Shoper API."""
from sqlalchemy import BigInteger, String, Integer, Numeric, Boolean, JSON, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawParcel(Base):
    __tablename__ = "raw_parcels"
    __table_args__ = (
        UniqueConstraint("store_id", "parcel_id", name="uq_raw_parcels_store_parcel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    parcel_id: Mapped[int] = mapped_column(BigInteger, index=True)
    order_id: Mapped[int] = mapped_column(BigInteger, index=True)
    shipping_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(10, 3), default=0)

    send_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    order_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    insurance: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    insurance_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cod: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cod_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    sent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    delivery_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    products: Mapped[list | None] = mapped_column(JSON, nullable=True)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
