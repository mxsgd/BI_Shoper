"""Which store a request may act for, and who may use the admin endpoints.

The store comes only from the signed session cookie that /api/shoper/app/entry issues when the
Shoper admin opens the app. A store_id sent by the client is never trusted: when one is sent it
must match the session, otherwise the request is refused.

Local development has no Shoper iframe and therefore no session. With DEV_STORE_ID set, requests
from this machine act as that store and may use the admin endpoints. The loopback check means a
DEV_STORE_ID left set on a deployed server still does not open it to the internet.
"""
from __future__ import annotations

import hmac
import time

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models.store import Store
from ..services.security.app_session import AppSessionError, create_session_token, verify_session_token

SESSION_COOKIE = "bi_shoper_session"
_LOOPBACK = {"127.0.0.1", "::1"}


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=get_settings().shoper_session_ttl_seconds,
        httponly=True,
        secure=True,
        samesite="none",  # required inside the Shoper admin iframe
        path="/",
    )


def _is_local(request: Request) -> bool:
    return request.client is not None and request.client.host in _LOOPBACK


def _dev_store_id(request: Request) -> int | None:
    dev = get_settings().dev_store_id
    return dev if dev and _is_local(request) else None


def _session_payload(token: str | None) -> dict | None:
    secret = get_settings().session_secret
    if not secret:
        # Without a secret anyone could sign a session (HMAC with an empty key), so none is valid.
        return None
    try:
        return verify_session_token(token or "", secret=secret)
    except AppSessionError:
        return None


async def _extend_session(response: Response, payload: dict, db: AsyncSession) -> None:
    """Re-issue the cookie once half its lifetime is gone, so an open panel stays signed in.

    Only for a store that is still active: after an uninstall the session is left to expire.
    """
    settings = get_settings()
    ttl = settings.shoper_session_ttl_seconds
    if payload["exp"] - time.time() > ttl / 2:
        return
    active = (await db.execute(
        select(Store.is_active).where(Store.id == payload["store_id"]))).scalar_one_or_none()
    if not active:
        return
    token = create_session_token(
        store_id=payload["store_id"], shop_id=payload.get("shop") or "",
        secret=settings.session_secret, ttl_seconds=ttl)
    set_session_cookie(response, token)


async def current_session(
    request: Request,
    response: Response,
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """{store_id, shop} of the caller, from the session cookie or the local dev fallback."""
    payload = _session_payload(session)
    if payload is not None:
        await _extend_session(response, payload, db)
        return {"store_id": payload["store_id"], "shop": payload.get("shop")}
    dev = _dev_store_id(request)
    if dev is not None:
        return {"store_id": dev, "shop": None}
    raise HTTPException(401, "No app session. Open the app from the Shoper admin panel.")


def check_store(requested: int | None, store_id: int) -> None:
    """A store_id sent in a path or body must be the session's store."""
    if requested is not None and requested != store_id:
        raise HTTPException(403, "store_id does not match the app session")


async def current_store_id(
    session: dict = Depends(current_session),
    requested: int | None = Query(default=None, alias="store_id"),
) -> int:
    """The store this request acts for. Use as `store_id: int = Depends(current_store_id)`."""
    check_store(requested, session["store_id"])
    return session["store_id"]


def ensure_owned(owner_store_id: int | None, store_id: int, what: str = "Job") -> None:
    """404 (not 403) for another store's object, so ids of other stores can't be probed."""
    if owner_store_id != store_id:
        raise HTTPException(404, f"{what} not found")


async def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> None:
    """Store management and global settings: operator only, never a merchant session."""
    expected = get_settings().admin_api_token
    if expected and x_admin_token and hmac.compare_digest(x_admin_token, expected):
        return
    if _dev_store_id(request) is not None:
        return
    raise HTTPException(403, "Admin only")
