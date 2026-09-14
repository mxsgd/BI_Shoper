from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models.app_setting import AppSetting

GA4_MEASUREMENT_ID_KEY = "ga4_measurement_id"
GA4_PROPERTY_ID_KEY = "ga4_property_id"


async def get_setting(db: AsyncSession, key: str) -> str | None:
    setting = await db.get(AppSetting, key)
    return setting.value if setting else None


async def set_setting(db: AsyncSession, key: str, value: str | None) -> None:
    stmt = pg_insert(AppSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": value})
    await db.execute(stmt)
    await db.commit()
