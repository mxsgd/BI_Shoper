"""CORE: dim_date - star schema dimension table (time dimension)."""
from sqlalchemy import Date, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from ...database import Base


class DimDate(Base):
    """Dimension table: date dimension for time-based analysis (seasonality, trends, YoY)."""
    __tablename__ = "dim_date"

    date_id: Mapped[str] = mapped_column(Date, primary_key=True)  # DATE type as primary key
    
    # Date components
    day: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer, index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    quarter: Mapped[int] = mapped_column(Integer, index=True)
    
    # Flags
    is_weekend: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
