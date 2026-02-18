from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    api_url: Mapped[str] = mapped_column(String(255))
    api_token: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_orders: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_products: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_customers: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
