import io

from app.dao import photo_metadata, storage
from tests.photo_helpers import RALEIGH_GPS, make_image


def test_upload_rejects_unsupported_content_type(client):
    resp = client.post(
        "/uploads/photo",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_rejects_oversized_file(client, monkeypatch):
    from app.services import uploads as upload_service

    monkeypatch.setattr(upload_service, "MAX_BYTES", 10)
    resp = client.post(
        "/uploads/photo",
        files={"file": ("bird.jpg", io.BytesIO(b"x" * 100), "image/jpeg")},
    )
    assert resp.status_code == 400


def test_upload_returns_503_when_storage_not_configured(client):
    # Default test settings have no SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY.
    resp = client.post(
        "/uploads/photo",
        files={"file": ("bird.jpg", io.BytesIO(make_image()), "image/jpeg")},
    )
    assert resp.status_code == 503


def test_upload_succeeds_when_storage_is_configured(client, monkeypatch):
    async def fake_upload_object(path, content, content_type):
        return f"https://fake.supabase.co/storage/v1/object/public/observation-photos/{path}"

    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "upload_object", fake_upload_object)

    resp = client.post(
        "/uploads/photo",
        files={"file": ("bird.jpg", io.BytesIO(make_image()), "image/jpeg")},
    )
    assert resp.status_code == 200
    photo_url = resp.json()["photo_url"]
    assert photo_url.startswith(
        "https://fake.supabase.co/storage/v1/object/public/observation-photos/"
    )
    assert photo_url.endswith(".jpg")


def test_upload_rejects_bytes_that_are_not_an_image(client):
    resp = client.post(
        "/uploads/photo",
        files={"file": ("bird.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
    )
    assert resp.status_code == 400


def test_upload_stores_stripped_copy_and_returns_metadata(client, monkeypatch):
    # The bucket is public — the stored bytes must not carry the GPS
    # position, but the response still reports it for When & Where.
    stored = {}

    async def fake_upload_object(path, content, content_type):
        stored["content"] = content
        return f"https://fake.supabase.co/storage/v1/object/public/observation-photos/{path}"

    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "upload_object", fake_upload_object)

    resp = client.post(
        "/uploads/photo",
        files={"file": ("bird.jpg", io.BytesIO(make_image(gps=RALEIGH_GPS, taken_at="2026:09:14 07:42:10")), "image/jpeg")},
    )
    assert resp.status_code == 200
    meta = resp.json()["photo_metadata"]
    assert round(meta["lat"], 3) == 35.780
    assert meta["taken_at"] == "2026-09-14T07:42:10"
    assert photo_metadata.read(stored["content"]) is None


def test_upload_without_metadata_returns_null_metadata(client, monkeypatch):
    async def fake_upload_object(path, content, content_type):
        return f"https://fake.supabase.co/{path}"

    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "upload_object", fake_upload_object)

    resp = client.post(
        "/uploads/photo",
        files={"file": ("bird.png", io.BytesIO(make_image(fmt="PNG")), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["photo_metadata"] is None
