"""RAW: GA4 daily page-level metrics."""
from sqlalchemy import Date, String, Integer, Numeric, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawGA4Page(Base):
    __tablename__ = "raw_ga4_pages"
    __table_args__ = (
        UniqueConstraint("date", "page_path", name="uq_ga4_pages_date_path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(Date, index=True)
    page_path: Mapped[str] = mapped_column(String(1000))
    page_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_views: Mapped[int] = mapped_column(Integer, default=0)
    avg_time_on_page: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    entrances: Mapped[int] = mapped_column(Integer, default=0)
    exits: Mapped[int] = mapped_column(Integer, default=0)
    bounce_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
