"""RAW: Order statuses from Shoper API - staging table."""
from sqlalchemy import String, Integer, JSON, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawStatus(Base):
    """Staging table for Order Statuses from Shoper API. 1:1 mapping with API response."""
    __tablename__ = "raw_statuses"
    __table_args__ = (
        UniqueConstraint("store_id", "status_id", name="uq_raw_statuses_store_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    status_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[int | None] = mapped_column(Integer, nullable=True)

    translations: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
