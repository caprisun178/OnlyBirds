from datetime import datetime

from pydantic import BaseModel


class PhotoMetadata(BaseModel):
    """Where/when a photo says it was taken (its EXIF) — a suggestion for
    the When & Where fields, never stored as-is. Each field is `None` when
    the photo didn't have it. See docs/features/photo-metadata.md."""

    lat: float | None = None
    lng: float | None = None
    taken_at: datetime | None = None  # naive — the photo's local wall-clock time


class PhotoUploadResponse(BaseModel):
    photo_url: str
    photo_metadata: PhotoMetadata | None = None
