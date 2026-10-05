"""Supabase Storage — raw HTTP calls only, no business logic.

Uploads a file to a public bucket and returns its public URL. No official
Python client is used here (one more dependency for two REST calls isn't
worth it); this talks to the Storage HTTP API directly with the service role
key, same as every other external call in `app/dao/`.

Docs: https://supabase.com/docs/guides/storage
"""

from __future__ import annotations

import httpx

from app.config import get_settings


class StorageNotConfigured(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY aren't set."""


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_service_role_key)


async def upload_object(path: str, content: bytes, content_type: str) -> str:
    """Uploads `content` to `{bucket}/{path}` (overwriting any existing file
    at that path) and returns its public URL. The bucket must already exist
    and be set public — Storage doesn't need to be aware of this project's
    identifications/observations types.
    """
    settings = get_settings()
    if not is_configured():
        raise StorageNotConfigured(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set."
        )

    bucket = settings.supabase_storage_bucket
    upload_url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        resp = await client.post(upload_url, headers=headers, content=content)
        resp.raise_for_status()

    return f"{settings.supabase_url}/storage/v1/object/public/{bucket}/{path}"
