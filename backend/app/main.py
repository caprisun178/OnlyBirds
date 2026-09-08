"""FastAPI application entrypoint.

    uvicorn app.main:app --reload      # from backend/
    uvicorn main:app --reload          # via the backend/main.py shim
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.routers import health, life_list, observations, sightings, species


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
    app.include_router(life_list.router)

    @app.get("/", tags=["health"])
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
        }

    return app


app = create_app()
