"""RAW: Producers (manufacturers) from Shoper API."""
from sqlalchemy import String, Integer, Boolean, JSON, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawProducer(Base):
    __tablename__ = "raw_producers"
    __table_args__ = (
        UniqueConstraint("store_id", "producer_id", name="uq_raw_producers_store_producer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    producer_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    web: Mapped[str | None] = mapped_column(String(500), nullable=True)
    isdefault: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    translations: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
