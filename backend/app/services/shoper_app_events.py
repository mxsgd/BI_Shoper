"""Domain handling of Shoper App Store lifecycle events (install/uninstall).

The router is responsible for transport + signature verification; this
service owns the database side and the auth_code exchange. All operations
are idempotent:

* repeated ``install`` for a known shop updates the existing installation
  (no duplicate rows - unique constraint on shoper_shop_id),
* replayed ``install`` whose auth_code was already consumed keeps an
  already-connected installation active,
* repeated ``uninstall`` is a no-op.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..models.shoper_app_installation import (
    INSTALLATION_ACTIVE,
    INSTALLATION_UNINSTALLED,
    ShoperAppInstallation,
)
from ..models.store import Store
from .security.shop_url import ShopUrlValidationError, rest_api_base, validate_shop_url
from .shoper_partner_auth import (
    ShoperPartnerAuthService,
    TokenEndpointError,
    TokenRequestRejectedError,
)

logger = logging.getLogger(__name__)


class AppStoreLifecycleAction(str, Enum):
    INSTALL = "install"
    UNINSTALL = "uninstall"
    UPGRADE = "upgrade"


@dataclass(frozen=True)
class AppStoreLifecycleEvent:
    action: AppStoreLifecycleAction
    shop_id: str
    shop_url: str
    application_code: str | None
    application_version: int | None
    trial: bool
    auth_code: str | None = None

    def __repr__(self) -> str:  # keep auth_code out of logs/tracebacks
        return (
            f"<AppStoreLifecycleEvent action={self.action.value} shop={self.shop_id} "
            f"version={self.application_version}>"
        )


class LifecycleEventError(RuntimeError):
    """Raised when an event cannot be processed; maps to an HTTP status."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class AppStoreEventProcessor:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings | None = None,
        auth_service: ShoperPartnerAuthService | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.auth = auth_service or ShoperPartnerAuthService(db, self.settings)

    async def handle_event(self, event: AppStoreLifecycleEvent) -> dict:
        if event.action == AppStoreLifecycleAction.INSTALL:
            return await self._handle_install(event)
        if event.action == AppStoreLifecycleAction.UNINSTALL:
            return await self._handle_uninstall(event)
        if event.action == AppStoreLifecycleAction.UPGRADE:
            return await self._handle_upgrade(event)
        raise LifecycleEventError("Unsupported action", status_code=400)

    # ------------------------------------------------------------------
    # install
    # ------------------------------------------------------------------
    async def _handle_install(self, event: AppStoreLifecycleEvent) -> dict:
        if not (event.auth_code or "").strip():
            raise LifecycleEventError("install event is missing auth_code", status_code=400)

        try:
            shop_origin = validate_shop_url(
                event.shop_url,
                allow_insecure=self.settings.shoper_allow_insecure_shop_url,
            )
        except ShopUrlValidationError as exc:
            raise LifecycleEventError(f"shop_url rejected: {exc}", status_code=400) from exc

        installation = await self._find_installation(event.shop_id)
        try:
            if installation is None:
                store = Store(
                    name=event.shop_id,
                    api_url=rest_api_base(shop_origin),
                    api_token="",
                    is_active=True,
                )
                self.db.add(store)
                await self.db.flush()
                installation = ShoperAppInstallation(
                    store_id=store.id,
                    shoper_shop_id=event.shop_id,
                    shop_url=shop_origin,
                )
                self.db.add(installation)
            else:
                store = await self.db.get(Store, installation.store_id)
                if store is None:
                    raise LifecycleEventError("Installation references a missing store")
                store.api_url = rest_api_base(shop_origin)
                store.is_active = True
                installation.shop_url = shop_origin

            installation.application_code = event.application_code
            installation.application_version = event.application_version
            installation.trial = event.trial
            installation.status = INSTALLATION_ACTIVE
            installation.installed_at = datetime.now(timezone.utc)
            installation.uninstalled_at = None
            installation.last_auth_error = None
            await self.db.commit()
        except LifecycleEventError:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

        had_valid_tokens = bool(installation.refresh_token_encrypted)
        try:
            await self.auth.exchange_auth_code(installation, event.auth_code)
        except (TokenRequestRejectedError, TokenEndpointError) as exc:
            if had_valid_tokens:
                # Replay of an already-consumed install event for a connected
                # shop: stay idempotent, keep the existing token pair.
                logger.warning(
                    "auth_code exchange failed for already-connected shop %s; "
                    "keeping existing tokens",
                    event.shop_id,
                )
                return {"status": "ok", "detail": "already installed"}
            raise LifecycleEventError(
                "auth_code exchange failed", status_code=409
            ) from exc

        logger.info("App installed for shop %s (store_id=%s)", event.shop_id, installation.store_id)
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # uninstall
    # ------------------------------------------------------------------
    async def _handle_uninstall(self, event: AppStoreLifecycleEvent) -> dict:
        installation = await self._find_installation(event.shop_id)
        if installation is None:
            # Unknown shop - treat as already uninstalled (idempotent).
            return {"status": "ok", "detail": "not installed"}

        try:
            installation.status = INSTALLATION_UNINSTALLED
            installation.uninstalled_at = datetime.now(timezone.utc)
            installation.access_token_encrypted = None
            installation.refresh_token_encrypted = None
            installation.token_expires_at = None

            store = await self.db.get(Store, installation.store_id)
            if store is not None:
                # Deactivate so the scheduler stops syncing; analytical data
                # in RAW/CORE stays (soft delete).
                store.is_active = False
                store.api_token = ""
                store.api_token_expires_at = None
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        logger.info("App uninstalled for shop %s (store_id=%s)", event.shop_id, installation.store_id)
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # upgrade
    # ------------------------------------------------------------------
    async def _handle_upgrade(self, event: AppStoreLifecycleEvent) -> dict:
        installation = await self._find_installation(event.shop_id)
        if installation is None:
            raise LifecycleEventError("upgrade for unknown shop", status_code=409)
        try:
            installation.application_version = event.application_version
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return {"status": "ok"}

    async def _find_installation(self, shop_id: str) -> ShoperAppInstallation | None:
        result = await self.db.execute(
            select(ShoperAppInstallation).where(
                ShoperAppInstallation.shoper_shop_id == shop_id
            )
        )
        return result.scalar_one_or_none()
