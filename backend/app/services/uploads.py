"""Business logic for the observation-photo upload endpoint (and
`POST /identify/photo?store=true`, which shares `store_photo()`)."""

from __future__ import annotations

import uuid

from app.dao import photo_metadata, storage
from app.models.upload import PhotoMetadata, PhotoUploadResponse

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",  # iPhone originals — stored as JPEG (see photo_metadata.strip)
    "image/heif",
}
# Big enough for full-size camera JPEGs (docs/features/bulk-import.md, open
# question 1, decided 2026-10-13); the stored copy is shrunk to STORED_MAX_EDGE.
MAX_BYTES = 25 * 1024 * 1024  # 25 MB
STORED_MAX_EDGE = 2048  # px, longest side of the stored copy

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
_HEIC_EXTENSIONS = (".heic", ".heif")


class UploadError(ValueError):
    """A validation failure — bad type or too large. Maps to a 400."""


def normalize_content_type(content_type: str | None, filename: str | None) -> str:
    """Browsers on Windows often send HEIC files with an empty or generic
    type (no OS-level HEIC registration), so fall back to the extension for
    those. Every other type is trusted as sent — `strip()` checks the real
    format anyway."""
    content_type = (content_type or "").lower()
    if content_type in ("", "application/octet-stream") and (filename or "").lower().endswith(_HEIC_EXTENSIONS):
        return "image/heic"
    return content_type or "application/octet-stream"


def validate(content_type: str, content: bytes) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadError(
            f"Unsupported image type '{content_type}'. Use JPEG, PNG, WebP, GIF, or HEIC."
        )
    if len(content) > MAX_BYTES:
        raise UploadError(
            f"Image is too large ({len(content) // 1024} KB). Max is {MAX_BYTES // (1024 * 1024)} MB."
        )


async def store_photo(content: bytes) -> tuple[str, PhotoMetadata | None]:
    """Reads where/when first (stripping removes it), then stores a
    metadata-free, size-capped copy — the bucket is public, see
    docs/features/photo-metadata.md. Raises `UploadError` for unreadable
    bytes and `storage.StorageNotConfigured` without Supabase."""
    metadata = photo_metadata.read(content)
    try:
        clean, clean_type = photo_metadata.strip(content, max_edge=STORED_MAX_EDGE)
    except photo_metadata.UnreadableImage as exc:
        raise UploadError(str(exc)) from exc

    path = f"{uuid.uuid4().hex}.{_EXTENSIONS[clean_type]}"
    photo_url = await storage.upload_object(path, clean, clean_type)
    return photo_url, PhotoMetadata(**metadata) if metadata else None


async def upload_observation_photo(
    filename: str, content_type: str, content: bytes
) -> PhotoUploadResponse:
    validate(normalize_content_type(content_type, filename), content)
    photo_url, metadata = await store_photo(content)
    return PhotoUploadResponse(photo_url=photo_url, photo_metadata=metadata)
