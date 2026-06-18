"""RAW: Product Groups (Zestawy wariantów) from Shoper API."""
from sqlalchemy import BigInteger, String, Boolean, Integer, JSON, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class RawProductGroup(Base):
    """
    Staging table for Product Groups from Shoper /product-groups endpoint.
    A product group ('zestaw wariantów') links related products that share
    the same variant structure (e.g. all mattresses of one model in different sizes).
    """
    __tablename__ = "raw_product_groups"
    __table_args__ = (
        UniqueConstraint("store_id", "group_id", name="uq_raw_product_groups_store_group"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)

    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Full translations JSON from Shoper
    translations: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ETL metadata
    loaded_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
