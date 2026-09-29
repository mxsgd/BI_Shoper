import asyncio
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..scheduler.jobs import get_ga4_resync_status, run_ga4_resync
from .access import current_session, require_admin
from ..services.app_settings_service import (
    GA4_MEASUREMENT_ID_KEY,
    GA4_PROPERTY_ID_KEY,
    get_setting,
    set_setting,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])
# GA4 settings are one global configuration, not per store: any panel may read them (the panel
# configures gtag from them), only the operator may change them or wipe and re-sync GA4 data.
signed_in = [Depends(current_session)]
admin = [Depends(require_admin)]

_MEASUREMENT_ID_RE = re.compile(r"^G-[A-Z0-9]{6,12}$")
_PROPERTY_ID_RE = re.compile(r"^\d{3,15}$")


class TrackingSettingsOut(BaseModel):
    ga4_measurement_id: str | None = None
    ga4_property_id: str | None = None
    ga4_property_id_is_override: bool = False


class TrackingSettingsUpdate(BaseModel):
    ga4_measurement_id: str | None = None
    ga4_property_id: str | None = None

    @field_validator("ga4_measurement_id")
    @classmethod
    def validate_measurement_id(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.strip().upper()
        if not _MEASUREMENT_ID_RE.match(v):
            raise ValueError("Nieprawidłowy format — oczekiwano np. G-XXXXXXXXXX")
        return v

    @field_validator("ga4_property_id")
    @classmethod
    def validate_property_id(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.strip()
        if not _PROPERTY_ID_RE.match(v):
            raise ValueError("Nieprawidłowy format — oczekiwano samych cyfr, np. 530034470")
        return v


@router.get("/tracking", response_model=TrackingSettingsOut, dependencies=signed_in)
async def get_tracking_settings(db: AsyncSession = Depends(get_db)):
    measurement_id = await get_setting(db, GA4_MEASUREMENT_ID_KEY)
    property_override = await get_setting(db, GA4_PROPERTY_ID_KEY)
    effective_property_id = property_override or get_settings().ga4_property_id or None
    return TrackingSettingsOut(
        ga4_measurement_id=measurement_id,
        ga4_property_id=effective_property_id,
        ga4_property_id_is_override=bool(property_override),
    )


@router.put("/tracking", response_model=TrackingSettingsOut, dependencies=admin)
async def update_tracking_settings(body: TrackingSettingsUpdate, db: AsyncSession = Depends(get_db)):
    await set_setting(db, GA4_MEASUREMENT_ID_KEY, body.ga4_measurement_id)
    await set_setting(db, GA4_PROPERTY_ID_KEY, body.ga4_property_id)
    effective_property_id = body.ga4_property_id or get_settings().ga4_property_id or None
    return TrackingSettingsOut(
        ga4_measurement_id=body.ga4_measurement_id,
        ga4_property_id=effective_property_id,
        ga4_property_id_is_override=bool(body.ga4_property_id),
    )


class Ga4ResyncRequest(BaseModel):
    days: int = Field(default=90, ge=1, le=365)


@router.post("/tracking/resync", dependencies=admin)
async def resync_ga4(body: Ga4ResyncRequest = Ga4ResyncRequest()):
    """Wipe previously-synced GA4 rows and backfill fresh from the currently
    configured property — call after switching GA4 tag/property so old data
    doesn't linger next to the new data."""
    status = get_ga4_resync_status()
    if status.get("status") == "running":
        return {"already_running": True, **status}

    asyncio.create_task(run_ga4_resync(body.days))
    return {"started": True, "days": body.days}


@router.get("/tracking/resync-status", dependencies=signed_in)
async def get_resync_status():
    return get_ga4_resync_status()
