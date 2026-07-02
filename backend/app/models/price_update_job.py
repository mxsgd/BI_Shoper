"""Persisted price update jobs and operation logs."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PriceUpdateJobRecord(Base):
    __tablename__ = "price_update_jobs"

    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20), index=True, default="PENDING")
    target_mode: Mapped[str] = mapped_column(String(20), default="product")
    csv_delimiter: Mapped[str] = mapped_column(String(20), default="semicolon")
    disable_extra_variants: Mapped[bool] = mapped_column(Boolean, default=True)
    duplicate_mode: Mapped[str] = mapped_column(String(20), default="error")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    warning: Mapped[int] = mapped_column(Integer, default=0)
    deactivated_variants: Mapped[int] = mapped_column(Integer, default=0)
    log_seq: Mapped[int] = mapped_column(Integer, default=0)
    logs_dropped: Mapped[int] = mapped_column(Integer, default=0)

    current_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_code: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_phase: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fatal_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_errors: Mapped[list | None] = mapped_column(JSONB, nullable=True)


class PriceUpdateLogRecord(Base):
    __tablename__ = "price_update_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("price_update_jobs.job_id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer, index=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    code: Mapped[str] = mapped_column(String(200), default="")
    old_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    stock_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
