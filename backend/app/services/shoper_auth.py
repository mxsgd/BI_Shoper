import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.store import Store

logger = logging.getLogger(__name__)

AUTH_TIMEOUT = 20.0
TOKEN_SAFETY_WINDOW = timedelta(minutes=5)


class ShoperAuthError(RuntimeError):
    """Base error for Shoper token renewal."""


class ShoperCredentialsMissingError(ShoperAuthError):
    """Raised when auto-renewal is configured without credentials."""


class ShoperTokenRefreshError(ShoperAuthError):
    """Raised when /auth does not return a usable token."""


@dataclass(frozen=True)
class ShoperCredentials:
    login: str
    password: str
    source: str


def has_store_credentials(store: Store) -> bool:
    if (store.api_login or "").strip() and (store.api_password or "").strip():
        return True
    return resolve_store_credentials(store) is not None


def resolve_store_credentials(store: Store) -> ShoperCredentials | None:
    login = (store.api_login or "").strip()
    password = (store.api_password or "").strip()
    if login and password:
        return ShoperCredentials(login=login, password=password, source="store")

    env_candidates: list[tuple[str, str, str]] = []
    if getattr(store, "id", None) is not None:
        env_candidates.append(
            (
                f"SHOPER_STORE_{store.id}_LOGIN",
                f"SHOPER_STORE_{store.id}_PASSWORD",
                f"env:SHOPER_STORE_{store.id}_*",
            )
        )
    env_candidates.extend(
        [
            ("SHOPER_DEFAULT_LOGIN", "SHOPER_DEFAULT_PASSWORD", "env:SHOPER_DEFAULT_*"),
            ("SHOPER_MK_LOGIN", "SHOPER_MK_PASSWORD", "env:SHOPER_MK_*"),
        ]
    )

    for login_key, password_key, source in env_candidates:
        env_login = (os.getenv(login_key) or "").strip()
        env_password = (os.getenv(password_key) or "").strip()
        if env_login and env_password:
            return ShoperCredentials(login=env_login, password=env_password, source=source)
    return None


def token_is_fresh(store: Store, now: datetime | None = None) -> bool:
    token = (store.api_token or "").strip()
    if not token:
        return False

    expires_at = store.api_token_expires_at
    if expires_at is None:
        # Legacy tokens have no expiry metadata; trust them until the API rejects them.
        return True

    now = now or datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now + TOKEN_SAFETY_WINDOW


async def ensure_store_token(
    db: AsyncSession,
    store: Store,
    *,
    force_refresh: bool = False,
) -> str:
    token = (store.api_token or "").strip()
    if token and not force_refresh and token_is_fresh(store):
        return token

    credentials = resolve_store_credentials(store)
    if credentials is None:
        if token and not force_refresh:
            return token
        raise ShoperCredentialsMissingError(
            "Brak danych logowania do automatycznego odswiezania tokenu Shopera. "
            "Ustaw api_login/api_password dla sklepu albo zmienne "
            "SHOPER_STORE_<id>_LOGIN / SHOPER_STORE_<id>_PASSWORD "
            "(ew. SHOPER_DEFAULT_* lub SHOPER_MK_*)."
        )

    return await refresh_store_token(db, store, credentials)


async def refresh_store_token(
    db: AsyncSession,
    store: Store,
    credentials: ShoperCredentials | None = None,
) -> str:
    credentials = credentials or resolve_store_credentials(store)
    if credentials is None:
        raise ShoperCredentialsMissingError(
            "Brak danych logowania do automatycznego odswiezania tokenu Shopera."
        )

    auth_url = f"{store.api_url.rstrip('/')}/auth"
    async with httpx.AsyncClient(timeout=AUTH_TIMEOUT) as client:
        response = await client.post(auth_url, auth=(credentials.login, credentials.password))

    if response.status_code != 200:
        raise ShoperTokenRefreshError(
            f"Shoper /auth zwrocil HTTP {response.status_code}: {response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ShoperTokenRefreshError("Shoper /auth zwrocil niepoprawny JSON.") from exc

    token = (payload.get("access_token") or "").strip()
    if not token:
        raise ShoperTokenRefreshError(f"Brak access_token w odpowiedzi /auth: {payload}")

    expires_in_raw = payload.get("expires_in") or 3600
    try:
        expires_in = int(expires_in_raw)
    except (TypeError, ValueError):
        expires_in = 3600

    now = datetime.now(timezone.utc)
    store.api_token = token
    store.api_token_updated_at = now
    store.api_token_expires_at = now + timedelta(seconds=max(expires_in - 60, 0))
    db.add(store)
    await db.commit()
    await db.refresh(store)
    logger.info("Refreshed Shoper token for store %s using %s", store.name, credentials.source)
    return token
