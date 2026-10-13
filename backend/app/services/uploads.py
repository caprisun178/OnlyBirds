"""Business logic for the observation-photo upload endpoint."""

from __future__ import annotations

import uuid

from app.dao import photo_metadata, storage
from app.models.upload import PhotoMetadata, PhotoUploadResponse

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_BYTES = 8 * 1024 * 1024  # 8 MB

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


class UploadError(ValueError):
    """A validation failure — bad type or too large. Maps to a 400."""


async def upload_observation_photo(
    filename: str, content_type: str, content: bytes
) -> PhotoUploadResponse:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadError(
            f"Unsupported image type '{content_type}'. Use JPEG, PNG, WebP, or GIF."
        )
    if len(content) > MAX_BYTES:
        raise UploadError(
            f"Image is too large ({len(content) // 1024} KB). Max is {MAX_BYTES // 1024} KB."
        )

    # Read where/when first — stripping removes it. The stored copy is
    # metadata-free because the bucket is public (see
    # docs/features/photo-metadata.md); the extension follows the format
    # actually written, not the client's claim.
    metadata = photo_metadata.read(content)
    try:
        clean, clean_type = photo_metadata.strip(content)
    except photo_metadata.UnreadableImage as exc:
        raise UploadError(str(exc)) from exc

    path = f"{uuid.uuid4().hex}.{_EXTENSIONS[clean_type]}"
    photo_url = await storage.upload_object(path, clean, clean_type)
    return PhotoUploadResponse(
        photo_url=photo_url,
        photo_metadata=PhotoMetadata(**metadata) if metadata else None,
    )
