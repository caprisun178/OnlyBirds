"""Describe & guess / photo identification endpoints.

    POST /identify/describe               free text -> ranked candidate photos
    GET  /identify/config                 {photo: bool} — is photo ID turned on
    POST /identify/photo                  photo upload -> ranked candidate photos (503 if off)
    POST /identify/{id}/select            record which candidate the user picked

See `docs/features/add-observation.md` for the describe flow and
`docs/features/bird-id.md` for the photo flow this feeds into.
"""

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings

from app.models.identification import (
    IdentifyRequest,
    IdentifyResponse,
    SelectCandidateRequest,
    SelectCandidateResponse,
)
from app.services import identify as identify_service
from app.services import uploads as upload_service

router = APIRouter(prefix="/identify", tags=["identify"])


@router.post("/describe", response_model=IdentifyResponse)
async def identify_describe(payload: IdentifyRequest):
    return await identify_service.describe_bird(payload)


@router.get("/config")
async def identify_config() -> dict:
    """Which identification methods this server offers — Add Observation
    hides the photo option when `photo` is false."""
    return {"photo": get_settings().photo_id_enabled}


@router.post("/photo", response_model=IdentifyResponse)
async def identify_photo(
    file: UploadFile = File(...),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
    observed_at: date | None = Form(None),
):
    if not get_settings().photo_id_enabled:
        raise HTTPException(
            status_code=503,
            detail="Photo identification is turned off right now. Describe the bird instead.",
        )
    content_type = file.content_type or "application/octet-stream"
    if content_type not in upload_service.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type '{content_type}'. Use JPEG, PNG, WebP, or GIF.",
        )
    content = await file.read()
    if len(content) > upload_service.MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image is too large ({len(content) // 1024} KB). Max is {upload_service.MAX_BYTES // 1024} KB.",
        )
    return await identify_service.identify_photo(content, lat=lat, lng=lng, observed_at=observed_at)


@router.post("/{identification_id}/select", response_model=SelectCandidateResponse)
async def identify_select(identification_id: str, payload: SelectCandidateRequest):
    result = await identify_service.select_candidate(
        identification_id, payload.species_code
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Identification not found")
    return result
