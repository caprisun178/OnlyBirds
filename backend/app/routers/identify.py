"""Describe & guess / photo identification endpoints.

    POST /identify/describe               free text -> ranked candidate photos
    POST /identify/photo                  photo upload -> ranked candidate photos
    POST /identify/{id}/select            record which candidate the user picked

See `docs/features/add-observation.md` for the describe flow and
`docs/features/bird-id.md` for the photo flow this feeds into.
"""

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.identification import (
    IdentifyRequest,
    IdentifyResponse,
    SelectCandidateRequest,
    SelectCandidateResponse,
)
from app.services import identify as identify_service
from app.services import uploads as upload_service  # validation + store_photo()

router = APIRouter(prefix="/identify", tags=["identify"])


@router.post("/describe", response_model=IdentifyResponse)
async def identify_describe(payload: IdentifyRequest):
    return await identify_service.describe_bird(payload)


@router.post("/photo", response_model=IdentifyResponse)
async def identify_photo(
    file: UploadFile = File(...),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
    observed_at: date | None = Form(None),
    store: bool = Form(False),
):
    """`store=true` (bulk import) also saves the photo — stripped and
    resized, same as `POST /uploads/photo` — and returns its `photo_url`,
    so the browser uploads each photo once instead of twice. See
    docs/features/bulk-import.md §4."""
    content = await file.read()
    try:
        upload_service.validate(upload_service.normalize_content_type(file.content_type, file.filename), content)
    except upload_service.UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await identify_service.identify_photo(
            content, lat=lat, lng=lng, observed_at=observed_at, store=store
        )
    except upload_service.UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{identification_id}/select", response_model=SelectCandidateResponse)
async def identify_select(identification_id: str, payload: SelectCandidateRequest):
    result = await identify_service.select_candidate(
        identification_id, payload.species_code
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Identification not found")
    return result
