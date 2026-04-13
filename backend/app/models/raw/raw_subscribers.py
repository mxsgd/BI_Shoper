"""RAW: Newsletter subscribers from Shoper API."""
from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawSubscriber(Base):
    __tablename__ = "raw_subscribers"
    __table_args__ = (
        UniqueConstraint("store_id", "subscriber_id", name="uq_raw_subscribers_store_sub"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    subscriber_id: Mapped[int] = mapped_column(Integer, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dateadd: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ipaddress: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lang_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
