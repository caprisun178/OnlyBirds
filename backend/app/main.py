"""FastAPI application entrypoint.

    uvicorn app.main:app --reload      # from backend/
    uvicorn main:app --reload          # via the backend/main.py shim
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.routers import (
    admin,
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
    trip,
    uploads,
    species,
    uploads,
    users,
)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
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
    app.include_router(species.router)
    app.include_router(sightings.router)
    app.include_router(observations.router)
    app.include_router(identify.router)
    app.include_router(uploads.router)
    app.include_router(geocoding.router)
    app.include_router(life_list.router)
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
