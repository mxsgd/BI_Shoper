"""CORE: dim_categories - star schema dimension table."""
from sqlalchemy import BigInteger, String, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class DimCategory(Base):
    """Dimension table: product categories. For category analysis."""
    __tablename__ = "dim_categories"

    category_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    category_name: Mapped[str] = mapped_column(String(255), index=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("dim_categories.category_id"), nullable=True, index=True)  # Self-referencing for tree
