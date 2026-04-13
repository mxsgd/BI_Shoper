"""RAW: GA4 daily traffic aggregates."""
from sqlalchemy import Date, Integer, Numeric, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawGA4Traffic(Base):
    __tablename__ = "raw_ga4_traffic"
    __table_args__ = (
        UniqueConstraint("date", name="uq_ga4_traffic_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, index=True)
    sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_users: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    page_views: Mapped[int] = mapped_column(Integer, default=0)
    bounce_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    avg_session_duration: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    engaged_sessions: Mapped[int] = mapped_column(Integer, default=0)
    events_count: Mapped[int] = mapped_column(Integer, default=0)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
