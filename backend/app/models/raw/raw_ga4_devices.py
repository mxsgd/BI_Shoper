"""RAW: GA4 daily device breakdown."""
from sqlalchemy import Date, String, Integer, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawGA4Device(Base):
    __tablename__ = "raw_ga4_devices"
    __table_args__ = (
        UniqueConstraint("date", "device_category", "browser", "os", name="uq_ga4_devices_date_dev"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, index=True)
    device_category: Mapped[str] = mapped_column(String(50), default="desktop")
    browser: Mapped[str] = mapped_column(String(100), default="(not set)")
    os: Mapped[str] = mapped_column(String(100), default="(not set)")
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    users: Mapped[int] = mapped_column(Integer, default=0)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
