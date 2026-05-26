from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    api_url: Mapped[str] = mapped_column(String(255))
    api_token: Mapped[str] = mapped_column(String(255), default="")
    api_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    api_token_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_orders: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_products: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_customers: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
