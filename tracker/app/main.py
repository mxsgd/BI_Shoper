# ──────────────────────────────────────────────────────────────
# Event Tracker — minimal self-contained tracking microservice
#
# Run locally:
#   cd tracker
#   pip install -r requirements.txt
#   uvicorn app.main:app --reload --port 8001
#
# Embed on any page:
#   <script src="http://localhost:8001/tracker.js" data-key="YOUR_KEY"></script>
# ──────────────────────────────────────────────────────────────

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import engine, Base
from .models import Event  # noqa: F401 — registers table with metadata
from .routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log = logging.getLogger(__name__)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("DB: schema ready (events table)")
    except Exception:
        log.exception("DB init failed — set DATABASE_URL (Railway Postgres). POST /api/event will fail until fixed.")
    yield
    await engine.dispose()


app = FastAPI(
    title="Event Tracker",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/swagger-ui",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    """Preferowany healthcheck (lekki, bez bazy)."""
    return {"status": "ok"}


@app.get("/docs", include_in_schema=False)
async def docs_health_compat():
    """Stare deploye Railway często mają healthcheck na /docs — zwracamy 200."""
    return {"status": "ok", "swagger": "/swagger-ui"}
