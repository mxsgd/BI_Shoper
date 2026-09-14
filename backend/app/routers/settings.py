import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..services.app_settings_service import (
    GA4_MEASUREMENT_ID_KEY,
    GA4_PROPERTY_ID_KEY,
    get_setting,
    set_setting,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

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


@router.get("/tracking", response_model=TrackingSettingsOut)
async def get_tracking_settings(db: AsyncSession = Depends(get_db)):
    measurement_id = await get_setting(db, GA4_MEASUREMENT_ID_KEY)
    property_override = await get_setting(db, GA4_PROPERTY_ID_KEY)
    effective_property_id = property_override or get_settings().ga4_property_id or None
    return TrackingSettingsOut(
        ga4_measurement_id=measurement_id,
        ga4_property_id=effective_property_id,
        ga4_property_id_is_override=bool(property_override),
    )


@router.put("/tracking", response_model=TrackingSettingsOut)
async def update_tracking_settings(body: TrackingSettingsUpdate, db: AsyncSession = Depends(get_db)):
    await set_setting(db, GA4_MEASUREMENT_ID_KEY, body.ga4_measurement_id)
    await set_setting(db, GA4_PROPERTY_ID_KEY, body.ga4_property_id)
    effective_property_id = body.ga4_property_id or get_settings().ga4_property_id or None
    return TrackingSettingsOut(
        ga4_measurement_id=body.ga4_measurement_id,
        ga4_property_id=effective_property_id,
        ga4_property_id_is_override=bool(body.ga4_property_id),
    )
