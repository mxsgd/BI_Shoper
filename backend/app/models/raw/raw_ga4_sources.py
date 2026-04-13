"""RAW: GA4 daily traffic by source/medium."""
from sqlalchemy import Date, String, Integer, Numeric, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawGA4Source(Base):
    __tablename__ = "raw_ga4_sources"
    __table_args__ = (
        UniqueConstraint("date", "source", "medium", name="uq_ga4_sources_date_src_med"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(255), default="(direct)")
    medium: Mapped[str] = mapped_column(String(255), default="(none)")
    campaign: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    users: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    engaged_sessions: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
