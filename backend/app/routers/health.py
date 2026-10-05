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
        # Matches `dao/ebird.py#_client()`'s actual gate (truthiness, not
        # `is not None`) — an env var present but set to an empty string
        # passes `is not None` while every real eBird call still rejects it
        # as unset, which made this report "configured" when it wasn't.
        "ebird_key_configured": bool(settings.ebird_api_key),
    }
