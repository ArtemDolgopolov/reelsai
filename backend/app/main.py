from contextlib import asynccontextmanager
import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.config import get_settings
from app.db import engine
from app.routers import competitors, health, reels
from app.routers.competitors import backfill_missing_transcripts
from app.services.seed import ensure_seed_data

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.seed_on_startup:
        with Session(engine) as session:
            ensure_seed_data(session)

    # Backfill spoken transcripts for every loaded creator in the background.
    thread = threading.Thread(
        target=backfill_missing_transcripts,
        name="transcript-backfill",
        daemon=True,
    )
    thread.start()
    logger.info("Started transcript backfill thread")
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(competitors.router, prefix="/api")
app.include_router(reels.router, prefix="/api")
