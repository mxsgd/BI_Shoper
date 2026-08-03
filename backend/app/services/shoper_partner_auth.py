"""Shoper Partner API (App Store) OAuth token management.

Flow (developers.shoper.pl, AppStore & Auth):

* install event delivers a one-time ``auth_code``,
* ``POST {shop_url}/webapi/rest/oauth/token`` with HTTP Basic auth
  (client_id = application ID, client_secret = App Store secret) and body
  ``grant_type=authorization_code&code={auth_code}`` returns
  access_token (90 days) + refresh_token (180 days),
* refresh: ``grant_type=refresh_token&refresh_token=...``; refresh tokens
  are single-use - every refresh returns a NEW pair (rotation).

Tokens are stored encrypted in ``shoper_app_installations``.
No token, secret or auth_code may ever be logged.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..models.shoper_app_installation import (
    INSTALLATION_ACTIVE,
    INSTALLATION_NEEDS_REAUTH,
    ShoperAppInstallation,
)
from .security.shop_url import rest_api_base
from .security.token_cipher import TokenCipher

logger = logging.getLogger(__name__)

TOKEN_HTTP_TIMEOUT = 20.0
# Refresh this long before the stored expiry.
TOKEN_SAFETY_WINDOW = timedelta(hours=24)
_TRANSIENT_RETRIES = 2
_TRANSIENT_BACKOFF = 1.0


class ShoperPartnerAuthError(RuntimeError):
    """Base error of the Partner OAuth service."""


class TokenEndpointError(ShoperPartnerAuthError):
    """Token endpoint returned an unusable response (5xx, bad JSON, timeout)."""


class TokenRequestRejectedError(ShoperPartnerAuthError):
    """Token endpoint rejected the request (4xx). Not retryable."""

    def __init__(self, message: str, *, error_code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.status = status


class InstallationNotConnectedError(ShoperPartnerAuthError):
    """Installation is missing, uninstalled or requires re-authorization."""


class TokenPair:
    __slots__ = ("access_token", "refresh_token", "expires_in", "scope")

    def __init__(self, access_token: str, refresh_token: str, expires_in: int, scope: str | None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in
        self.scope = scope

    def __repr__(self) -> str:  # never leak token material
        return f"<TokenPair expires_in={self.expires_in}>"


# Per-installation asyncio locks guarding concurrent refresh.
_refresh_locks: dict[int, asyncio.Lock] = {}


def _get_refresh_lock(installation_id: int) -> asyncio.Lock:
    lock = _refresh_locks.get(installation_id)
    if lock is None:
        lock = asyncio.Lock()
        _refresh_locks[installation_id] = lock
    return lock


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class ShoperPartnerAuthService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings | None = None,
        cipher: TokenCipher | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.cipher = cipher or TokenCipher(self.settings.shoper_token_cipher_key)
        self._transport = transport  # test hook (httpx.MockTransport)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    async def _token_request(self, shop_url: str, form: dict[str, str]) -> TokenPair:
        url = f"{rest_api_base(shop_url)}/oauth/token"
        auth = (self.settings.shoper_app_id, self.settings.shoper_app_secret)

        last_transient: Exception | None = None
        for attempt in range(1 + _TRANSIENT_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=TOKEN_HTTP_TIMEOUT, transport=self._transport
                ) as client:
                    response = await client.post(url, data=form, auth=auth)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_transient = exc
                if attempt < _TRANSIENT_RETRIES:
                    await asyncio.sleep(_TRANSIENT_BACKOFF * (attempt + 1))
                continue

            if response.status_code in (429,) or response.status_code >= 500:
                last_transient = TokenEndpointError(
                    f"Token endpoint returned HTTP {response.status_code}"
                )
                if attempt < _TRANSIENT_RETRIES:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait = float(retry_after) if retry_after else _TRANSIENT_BACKOFF * (attempt + 1)
                    except ValueError:
                        wait = _TRANSIENT_BACKOFF * (attempt + 1)
                    await asyncio.sleep(wait)
                continue

            if response.status_code != 200:
                error_code = None
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        error_code = body.get("error")
                except ValueError:
                    pass
                # Never include the response body - it could echo the code/token.
                raise TokenRequestRejectedError(
                    f"Token endpoint rejected the request (HTTP {response.status_code})",
                    error_code=error_code,
                    status=response.status_code,
                )

            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                raise TokenEndpointError(
                    f"Token endpoint returned unexpected Content-Type: {content_type or '(none)'}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise TokenEndpointError("Token endpoint returned invalid JSON") from exc
            if not isinstance(payload, dict):
                raise TokenEndpointError("Token endpoint returned non-object JSON")

            access_token = str(payload.get("access_token") or "").strip()
            refresh_token = str(payload.get("refresh_token") or "").strip()
            if not access_token:
                raise TokenEndpointError("Token response is missing access_token")
            if not refresh_token:
                raise TokenEndpointError("Token response is missing refresh_token")

            try:
                expires_in = int(payload.get("expires_in") or 0)
            except (TypeError, ValueError):
                expires_in = 0
            if expires_in <= 0:
                expires_in = 90 * 24 * 3600  # documented default: 90 days

            scope = payload.get("scope")
            return TokenPair(access_token, refresh_token, expires_in, scope)

        raise TokenEndpointError(f"Token endpoint unavailable: {last_transient}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def exchange_auth_code(self, installation: ShoperAppInstallation, auth_code: str) -> str:
        """Exchange a one-time install auth_code for a token pair; returns access token."""
        auth_code = (auth_code or "").strip()
        if not auth_code:
            raise TokenRequestRejectedError("auth_code is empty", error_code="invalid_request")
        pair = await self._token_request(
            installation.shop_url,
            {"grant_type": "authorization_code", "code": auth_code},
        )
        await self._store_pair(installation, pair)
        return pair.access_token

    async def refresh_access_token(self, installation: ShoperAppInstallation) -> str:
        """Refresh the token pair using the stored refresh token; returns access token."""
        if not installation.refresh_token_encrypted:
            raise InstallationNotConnectedError(
                "No refresh token stored - the shop must reinstall the application."
            )
        refresh_token = self.cipher.decrypt(installation.refresh_token_encrypted)
        try:
            pair = await self._token_request(
                installation.shop_url,
                {"grant_type": "refresh_token", "refresh_token": refresh_token},
            )
        except TokenRequestRejectedError as exc:
            if exc.error_code == "invalid_grant" or exc.status in (400, 401):
                await self._mark_needs_reauth(installation, reason=exc.error_code or f"http_{exc.status}")
            raise
        await self._store_pair(installation, pair)
        return pair.access_token

    async def ensure_store_access_token(
        self, installation: ShoperAppInstallation, *, force_refresh: bool = False
    ) -> str:
        """Return a valid access token, refreshing when inside the safety window.

        Concurrent callers for the same installation are serialized with a
        per-installation lock; after acquiring it the freshness check is
        repeated so only one request hits the token endpoint.
        """
        if installation.status != INSTALLATION_ACTIVE:
            raise InstallationNotConnectedError(
                f"Installation is not active (status={installation.status})."
            )

        if not force_refresh and self._token_is_fresh(installation):
            return self.cipher.decrypt(installation.access_token_encrypted)

        lock = _get_refresh_lock(installation.id)
        async with lock:
            # Another coroutine may have refreshed while we waited.
            await self.db.refresh(installation)
            if not force_refresh and self._token_is_fresh(installation):
                return self.cipher.decrypt(installation.access_token_encrypted)
            return await self.refresh_access_token(installation)

    async def revoke_or_remove_credentials(self, installation: ShoperAppInstallation) -> None:
        """Wipe stored token material (uninstall)."""
        installation.access_token_encrypted = None
        installation.refresh_token_encrypted = None
        installation.token_expires_at = None
        installation.token_updated_at = _utcnow()
        self.db.add(installation)
        await self.db.commit()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _token_is_fresh(self, installation: ShoperAppInstallation) -> bool:
        if not installation.access_token_encrypted:
            return False
        expires_at = _aware(installation.token_expires_at)
        if expires_at is None:
            return False
        return expires_at > _utcnow() + TOKEN_SAFETY_WINDOW

    async def _store_pair(self, installation: ShoperAppInstallation, pair: TokenPair) -> None:
        now = _utcnow()
        try:
            installation.access_token_encrypted = self.cipher.encrypt(pair.access_token)
            installation.refresh_token_encrypted = self.cipher.encrypt(pair.refresh_token)
            installation.token_expires_at = now + timedelta(seconds=pair.expires_in)
            installation.token_updated_at = now
            if pair.scope:
                installation.scopes = str(pair.scope)
            installation.last_auth_error = None
            self.db.add(installation)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def _mark_needs_reauth(self, installation: ShoperAppInstallation, *, reason: str) -> None:
        try:
            installation.status = INSTALLATION_NEEDS_REAUTH
            installation.last_auth_error = reason[:500]
            self.db.add(installation)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        logger.warning(
            "Shoper installation %s (store %s) marked as needs_reauth (%s)",
            installation.id,
            installation.store_id,
            reason,
        )


async def get_active_installation(
    db: AsyncSession, store_id: int
) -> ShoperAppInstallation | None:
    result = await db.execute(
        select(ShoperAppInstallation).where(ShoperAppInstallation.store_id == store_id)
    )
    return result.scalar_one_or_none()
