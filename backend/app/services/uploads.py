"""Business logic for the observation-photo upload endpoint."""

from __future__ import annotations

import uuid

from app.dao import storage

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_BYTES = 8 * 1024 * 1024  # 8 MB


class UploadError(ValueError):
    """A validation failure — bad type or too large. Maps to a 400."""


async def upload_observation_photo(
    filename: str, content_type: str, content: bytes
) -> str:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadError(
            f"Unsupported image type '{content_type}'. Use JPEG, PNG, WebP, or GIF."
        )
    if len(content) > MAX_BYTES:
        raise UploadError(
            f"Image is too large ({len(content) // 1024} KB). Max is {MAX_BYTES // 1024} KB."
        )

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else content_type.split("/")[-1]
    path = f"{uuid.uuid4().hex}.{ext}"
    return await storage.upload_object(path, content, content_type)
