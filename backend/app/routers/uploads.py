"""Photo upload endpoint — object storage for the Add Observation field-notes
photo (and, later, avatars).

    POST /uploads/photo    multipart file -> {photo_url}

Returns 503 while `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` aren't set —
see docs/features/add-observation.md.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.dao.storage import StorageNotConfigured
from app.models.upload import PhotoUploadResponse
from app.services import uploads as upload_service

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/photo", response_model=PhotoUploadResponse)
async def upload_photo(file: UploadFile = File(...)):
    content = await file.read()
    try:
        photo_url = await upload_service.upload_observation_photo(
            file.filename or "photo",
            file.content_type or "application/octet-stream",
            content,
        )
    except upload_service.UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PhotoUploadResponse(photo_url=photo_url)
