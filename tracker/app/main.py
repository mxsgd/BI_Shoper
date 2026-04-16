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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Event Tracker",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
