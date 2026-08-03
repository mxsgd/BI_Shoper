"""Single entry point for obtaining Shoper API access per store.

Auth modes:

* ``partner_oauth``  - App Store installation with OAuth tokens (production),
* ``legacy_webapi``  - DEPRECATED login/password POST /auth; available only
                       when SHOPER_ENABLE_LEGACY_WEBAPI is set and ONLY for
                       stores without an App Store installation,
* ``disconnected``   - no way to authorize the store.

A store that has an App Store installation NEVER falls back to legacy
credentials, even if they are present.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..models.shoper_app_installation import INSTALLATION_ACTIVE
from ..models.store import Store
from . import shoper_auth as legacy_auth
from .shoper_client import ShoperClient
from .shoper_partner_auth import (
    InstallationNotConnectedError,
    ShoperPartnerAuthService,
    get_active_installation,
)

logger = logging.getLogger(__name__)

AUTH_MODE_PARTNER = "partner_oauth"
AUTH_MODE_LEGACY = "legacy_webapi"
AUTH_MODE_DISCONNECTED = "disconnected"


class StoreDisconnectedError(RuntimeError):
    """The store has no usable authorization method."""


async def store_auth_mode(db: AsyncSession, store: Store) -> str:
    settings = get_settings()
    installation = await get_active_installation(db, store.id)
    if installation is not None:
        if installation.status == INSTALLATION_ACTIVE:
            return AUTH_MODE_PARTNER
        return AUTH_MODE_DISCONNECTED
    if settings.shoper_enable_legacy_webapi and legacy_auth.has_store_credentials(store):
        return AUTH_MODE_LEGACY
    return AUTH_MODE_DISCONNECTED


async def ensure_store_access_token(
    db: AsyncSession,
    store: Store,
    *,
    force_refresh: bool = False,
    settings: Settings | None = None,
) -> str:
    """Return a valid access token for the store, refreshing when needed."""
    settings = settings or get_settings()
    installation = await get_active_installation(db, store.id)

    if installation is not None:
        # App Store-installed shop: partner OAuth only, never legacy.
        if installation.status != INSTALLATION_ACTIVE:
            raise StoreDisconnectedError(
                f"Sklep '{store.name}' wymaga ponownej instalacji/autoryzacji aplikacji "
                f"(status: {installation.status})."
            )
        svc = ShoperPartnerAuthService(db, settings)
        try:
            return await svc.ensure_store_access_token(installation, force_refresh=force_refresh)
        except InstallationNotConnectedError as exc:
            raise StoreDisconnectedError(str(exc)) from exc

    if settings.shoper_enable_legacy_webapi:
        # DEPRECATED path - kept only for stores not yet migrated.
        return await legacy_auth.ensure_store_token(db, store, force_refresh=force_refresh)

    raise StoreDisconnectedError(
        f"Sklep '{store.name}' nie ma aktywnej instalacji App Store, a tryb legacy "
        "WebAPI jest wylaczony (SHOPER_ENABLE_LEGACY_WEBAPI)."
    )


def build_store_client(store: Store, token: str, on_unauthorized=None) -> ShoperClient:
    """Create a ShoperClient bound to this store's API URL and store_id."""
    return ShoperClient(
        store.api_url, token, on_unauthorized=on_unauthorized, store_id=store.id
    )
