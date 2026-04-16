import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import Event

logger = logging.getLogger(__name__)

router = APIRouter()

TRACKER_JS = (Path(__file__).resolve().parent.parent / "tracker.js").read_text(encoding="utf-8")


# ── GET /tracker.js ──────────────────────────────────────────────
@router.get("/tracker.js")
async def serve_tracker():
    return Response(content=TRACKER_JS, media_type="application/javascript")


# ── POST /api/event ──────────────────────────────────────────────
class EventPayload(BaseModel):
    apiKey: str
    event: str
    user_id: str
    url: str
    timestamp: int
    metadata: dict[str, Any] = {}


@router.post("/api/event", status_code=201)
async def receive_event(payload: EventPayload, db: AsyncSession = Depends(get_db)):
    if not payload.apiKey or not payload.event:
        raise HTTPException(status_code=400, detail="apiKey and event are required")

    ev = Event(
        api_key=payload.apiKey,
        event_name=payload.event,
        user_id=payload.user_id,
        url=payload.url,
        timestamp=payload.timestamp,
        metadata_=payload.metadata,
    )
    db.add(ev)
    await db.commit()

    logger.info("event=%s user=%s url=%s", payload.event, payload.user_id, payload.url)
    return {"ok": True}
