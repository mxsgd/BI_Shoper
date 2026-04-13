"""RAW: User groups from Shoper API."""
from sqlalchemy import String, Integer, Numeric, Boolean, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawUserGroup(Base):
    __tablename__ = "raw_user_groups"
    __table_args__ = (
        UniqueConstraint("store_id", "group_id", name="uq_raw_user_groups_store_group"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    group_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discount: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    price_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_add: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
