from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

# Installation status values
INSTALLATION_ACTIVE = "active"
INSTALLATION_UNINSTALLED = "uninstalled"
INSTALLATION_NEEDS_REAUTH = "needs_reauth"


class ShoperAppInstallation(Base):
    """One App Store installation of this application in a Shoper shop.

    Tokens are stored encrypted (Fernet) - see TokenCipher. They must never
    be returned by API endpoints or written to logs.
    """

    __tablename__ = "shoper_app_installations"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), unique=True, index=True
    )
    # Shop identifier sent by Shoper in lifecycle/iframe requests.
    shoper_shop_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    # Validated shop origin, e.g. https://myshop.shoparena.pl
    shop_url: Mapped[str] = mapped_column(String(255))
    application_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    application_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trial: Mapped[bool] = mapped_column(Boolean, default=False)

    # Encrypted token material (Fernet ciphertext).
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default=INSTALLATION_ACTIVE, index=True)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_auth_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # never include token columns
        return (
            f"<ShoperAppInstallation id={self.id} store_id={self.store_id} "
            f"shop={self.shoper_shop_id} status={self.status}>"
        )
