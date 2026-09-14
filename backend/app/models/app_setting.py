from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class AppSetting(Base):
    """Generic key/value store for small app-wide config (e.g. the dashboard's own gtag id)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
