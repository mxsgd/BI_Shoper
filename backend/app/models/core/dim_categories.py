"""CORE: dim_categories - star schema dimension table."""
from sqlalchemy import BigInteger, String, ForeignKey, ForeignKeyConstraint, PrimaryKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class DimCategory(Base):
    """Dimension table: product categories. For category analysis."""
    __tablename__ = "dim_categories"
    # Shoper ids are per-shop sequences (every shop has an order #1), so a row is identified by
    # (store_id, <shoper id>). store_id leads the key, which also serves the per-store filters.
    __table_args__ = (
        PrimaryKeyConstraint("store_id", "category_id", name="dim_categories_pkey"),
        ForeignKeyConstraint(
            ["store_id", "parent_id"],
            ["dim_categories.store_id", "dim_categories.category_id"],
            name="dim_categories_parent_fkey",
        ),
    )

    category_id: Mapped[int] = mapped_column(BigInteger)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    category_name: Mapped[str] = mapped_column(String(255), index=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)  # Self-referencing for tree
