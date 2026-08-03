"""Shoper App Store endpoints: lifecycle events and iframe entry.

Transport layer only - HMAC verification is delegated to
ShoperSignatureValidator, domain logic to AppStoreEventProcessor and
token handling to ShoperPartnerAuthService.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models.shoper_app_installation import INSTALLATION_ACTIVE, ShoperAppInstallation
from ..models.store import Store
from ..services.security.app_session import (
    AppSessionError,
    create_session_token,
    verify_session_token,
)
from ..services.security.shoper_signature import (
    InvalidSignatureError,
    MissingParameterError,
    MissingSignatureError,
    ShoperSignatureValidator,
    StaleTimestampError,
)
from ..services.shoper_app_events import (
    AppStoreEventProcessor,
    AppStoreLifecycleAction,
    AppStoreLifecycleEvent,
    LifecycleEventError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shoper", tags=["shoper-app"])

SESSION_COOKIE = "bi_shoper_session"


def _validator() -> ShoperSignatureValidator:
    settings = get_settings()
    if not settings.shoper_appstore_enabled:
        raise HTTPException(status_code=404, detail="App Store integration is disabled")
    try:
        return ShoperSignatureValidator(settings.shoper_app_secret)
    except ValueError as exc:
        # Config error; never echo the secret.
        raise HTTPException(status_code=503, detail="App Store integration is misconfigured") from exc


# ----------------------------------------------------------------------
# Lifecycle events (install / uninstall / upgrade)
# ----------------------------------------------------------------------
@router.post("/app-store/event")
async def app_store_event(request: Request, db: AsyncSession = Depends(get_db)):
    validator = _validator()

    form = await request.form()
    params: dict[str, str] = {k: str(v) for k, v in form.items()}

    try:
        validator.verify(params, required=("shop", "action"))
    except MissingSignatureError:
        raise HTTPException(status_code=401, detail="Missing authentication credentials")
    except MissingParameterError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidSignatureError:
        raise HTTPException(status_code=401, detail="Invalid signature")

    raw_action = params.get("action", "")
    try:
        action = AppStoreLifecycleAction(raw_action)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown action")

    shop_url = (params.get("shop_url") or "").strip()
    if action == AppStoreLifecycleAction.INSTALL and not shop_url:
        raise HTTPException(status_code=400, detail="Missing required parameter: shop_url")

    raw_version = (params.get("application_version") or "").strip()
    application_version: int | None = None
    if raw_version:
        try:
            application_version = int(raw_version)
        except ValueError:
            raise HTTPException(status_code=400, detail="application_version must be an integer")

    event = AppStoreLifecycleEvent(
        action=action,
        shop_id=params["shop"],
        shop_url=shop_url,
        application_code=(params.get("application_code") or None),
        application_version=application_version,
        trial=(params.get("trial") or "0").strip() in ("1", "true"),
        auth_code=(params.get("auth_code") or None),
    )

    processor = AppStoreEventProcessor(db)
    try:
        result = await processor.handle_event(event)
    except LifecycleEventError as exc:
        # Controlled error; message never contains secrets or the auth_code.
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    return JSONResponse(result)


# ----------------------------------------------------------------------
# Iframe entry + app session
# ----------------------------------------------------------------------
@router.get("/app/entry")
async def app_iframe_entry(request: Request, db: AsyncSession = Depends(get_db)):
    """Entry point loaded by the Shoper admin iframe.

    Verifies the signed query parameters (shop, place, timestamp, hash),
    maps the shop to a local store and issues a short-lived session cookie.
    Shoper API tokens are never exposed to the frontend.
    """
    settings = get_settings()
    validator = _validator()

    params: dict[str, str] = {k: str(v) for k, v in request.query_params.items()}
    try:
        validator.verify_with_timestamp(
            params,
            required=("shop", "timestamp"),
            max_age_seconds=settings.shoper_iframe_max_age_seconds,
        )
    except MissingSignatureError:
        raise HTTPException(status_code=401, detail="Missing authentication credentials")
    except MissingParameterError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except StaleTimestampError:
        raise HTTPException(status_code=401, detail="Request expired")
    except InvalidSignatureError:
        raise HTTPException(status_code=401, detail="Invalid signature")

    shop_id = params["shop"]
    result = await db.execute(
        select(ShoperAppInstallation).where(ShoperAppInstallation.shoper_shop_id == shop_id)
    )
    installation = result.scalar_one_or_none()
    if installation is None or installation.status != INSTALLATION_ACTIVE:
        raise HTTPException(status_code=403, detail="Application is not installed for this shop")

    store = await db.get(Store, installation.store_id)
    if store is None or not store.is_active:
        raise HTTPException(status_code=403, detail="Store is inactive")

    token = create_session_token(
        store_id=store.id,
        shop_id=shop_id,
        secret=settings.session_secret,
        ttl_seconds=settings.shoper_session_ttl_seconds,
    )

    response = RedirectResponse(url=settings.shoper_panel_redirect_url, status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.shoper_session_ttl_seconds,
        httponly=True,
        secure=True,
        samesite="none",  # required inside the Shoper admin iframe
        path="/",
    )
    return response


async def require_app_session(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    """FastAPI dependency: validated app session payload (store_id, shop)."""
    settings = get_settings()
    try:
        return verify_session_token(session or "", secret=settings.session_secret)
    except AppSessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/app/session")
async def app_session_info(payload: dict = Depends(require_app_session)):
    """Session context for the frontend (which store to query). No tokens."""
    return {"store_id": payload["store_id"], "shop": payload.get("shop")}
