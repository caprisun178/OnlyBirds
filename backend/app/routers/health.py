"""Health / readiness — roadmap step 1's "hello world" endpoint."""

from fastapi import APIRouter

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "ebird_key_configured": settings.ebird_api_key is not None,
    }
