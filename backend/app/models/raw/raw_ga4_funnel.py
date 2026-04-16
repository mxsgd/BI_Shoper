"""RAW: GA4 daily e-commerce funnel event counts."""
from sqlalchemy import Date, Integer, Numeric, UniqueConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawGA4Funnel(Base):
    __tablename__ = "raw_ga4_funnel"
    __table_args__ = (
        UniqueConstraint("date", name="uq_ga4_funnel_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, index=True)
    view_item: Mapped[int] = mapped_column(Integer, default=0)
    add_to_cart: Mapped[int] = mapped_column(Integer, default=0)
    begin_checkout: Mapped[int] = mapped_column(Integer, default=0)
    add_payment_info: Mapped[int] = mapped_column(Integer, default=0)
    purchase: Mapped[int] = mapped_column(Integer, default=0)
    remove_from_cart: Mapped[int] = mapped_column(Integer, default=0)
    add_to_cart_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    purchase_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RawGA4FunnelDevice(Base):
    __tablename__ = "raw_ga4_funnel_devices"
    __table_args__ = (
        UniqueConstraint("date", "device_category", name="uq_ga4_funnel_dev_date_device"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, index=True)
    device_category: Mapped[str] = mapped_column(String(50))
    view_item: Mapped[int] = mapped_column(Integer, default=0)
    add_to_cart: Mapped[int] = mapped_column(Integer, default=0)
    begin_checkout: Mapped[int] = mapped_column(Integer, default=0)
    add_payment_info: Mapped[int] = mapped_column(Integer, default=0)
    purchase: Mapped[int] = mapped_column(Integer, default=0)
    remove_from_cart: Mapped[int] = mapped_column(Integer, default=0)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RawGA4CartProduct(Base):
    __tablename__ = "raw_ga4_cart_products"
    __table_args__ = (
        UniqueConstraint("date", "item_name", name="uq_ga4_cart_prod_date_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, index=True)
    item_name: Mapped[str] = mapped_column(String(500))
    item_id: Mapped[str] = mapped_column(String(100), nullable=True)
    add_to_cart_count: Mapped[int] = mapped_column(Integer, default=0)
    purchase_count: Mapped[int] = mapped_column(Integer, default=0)
    item_revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
