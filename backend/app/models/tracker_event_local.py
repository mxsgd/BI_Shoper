"""Lokalna kopia eventów z trackera (Railway) — sync przy starcie dev."""
import uuid

from sqlalchemy import String, BigInteger, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class TrackerEventLocal(Base):
    __tablename__ = "tracker_events_local"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    api_key: Mapped[str] = mapped_column(String(128), index=True)
    event_name: Mapped[str] = mapped_column(String(100), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[int] = mapped_column(BigInteger, index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    synced_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
