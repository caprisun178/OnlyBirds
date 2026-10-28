"""FastAPI application entrypoint.

    uvicorn app.main:app --reload      # from backend/
    uvicorn main:app --reload          # via the backend/main.py shim
"""

import logging
from contextlib import asynccontextmanager
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import get_settings
from app.routers import (
    admin,
    auth,
    feedback,
    geocoding,
    health,
    identify,
    life_list,
    notifications,
    observations,
    pins,
    quiz,
    sightings,
    species,
    stickers,
    trip,
    uploads,
    users,
)


logger = logging.getLogger(__name__)


def _warm_up_photo_id() -> None:
    try:
        from app.dao import bioclip_classifier

        bioclip_classifier.warm_up()
        logger.info("Photo ID model loaded")
    except Exception:  # noqa: BLE001 — never crash the server over a warm-up
        logger.exception("Photo ID warm-up failed; it will load on first use instead")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    # Background thread: loading the photo-ID model takes a while and must
    # not delay startup or block requests. Failure only means the first
    # photo ID loads it instead.
    if settings.photo_id_enabled and settings.photo_id_preload:
        threading.Thread(target=_warm_up_photo_id, name="photo-id-warm-up", daemon=True).start()
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        lifespan=_lifespan,
        title=settings.app_name,
        version=__version__,
        summary="iNaturalist + eBird + personal life list, normalized into one API.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(species.router)
    app.include_router(sightings.router)
    app.include_router(observations.router)
    app.include_router(identify.router)
    app.include_router(uploads.router)
    app.include_router(geocoding.router)
    app.include_router(life_list.router)
    app.include_router(stickers.router)
    app.include_router(users.router)
    app.include_router(quiz.router)
    app.include_router(trip.router)
    app.include_router(pins.router)
    app.include_router(notifications.router)
    app.include_router(feedback.router)
    app.include_router(admin.router)

    @app.get("/", tags=["health"])
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
        }

    return app


app = create_app()
app.mount(
    "/static/stickers",
    StaticFiles(directory=Path(__file__).resolve().parent / "data" / "stickers"),
    name="sticker-art",
)
