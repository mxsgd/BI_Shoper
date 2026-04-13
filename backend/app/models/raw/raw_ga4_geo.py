"""RAW: GA4 daily geographic breakdown."""
from sqlalchemy import Date, String, Integer, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawGA4Geo(Base):
    __tablename__ = "raw_ga4_geo"
    __table_args__ = (
        UniqueConstraint("date", "country", "city", name="uq_ga4_geo_date_loc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, index=True)
    country: Mapped[str] = mapped_column(String(100), default="(not set)")
    city: Mapped[str] = mapped_column(String(200), default="(not set)")
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    users: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
