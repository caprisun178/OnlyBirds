"""Bulk photo import backend — docs/features/bulk-import.md §4.

`POST /identify/photo` with `store=true`, the HEIC content-type fallback,
`import_batch_id` on observations, and `DELETE /users/{id}/imports/{batch}`.
"""

import io

from app.dao import bioclip_classifier, photo_metadata, storage
from tests.photo_helpers import RALEIGH_GPS, make_image


def _fake_classify(image_bytes, top_k=6, candidates=None):
    return [{"scientific_name": "Cardinalis cardinalis", "common_name": "Northern Cardinal", "species_code": "norcar", "confidence": 0.9}]


def _fake_storage(monkeypatch):
    stored = {}

    async def fake_upload_object(path, content, content_type):
        stored["content"], stored["content_type"] = content, content_type
        return f"https://fake.supabase.co/storage/v1/object/public/observation-photos/{path}"

    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "upload_object", fake_upload_object)
    return stored


def test_identify_with_store_returns_stripped_photo_url(client, monkeypatch):
    monkeypatch.setattr(bioclip_classifier, "classify", _fake_classify)
    stored = _fake_storage(monkeypatch)

    resp = client.post(
        "/identify/photo",
        files={"file": ("bird.jpg", io.BytesIO(make_image(gps=RALEIGH_GPS)), "image/jpeg")},
        data={"store": "true"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["photo_url"].endswith(".jpg")
    assert body["photo_metadata"]["lat"] is not None  # read before stripping
    assert photo_metadata.read(stored["content"]) is None  # public copy has no GPS


def test_identify_without_store_never_touches_storage(client, monkeypatch):
    monkeypatch.setattr(bioclip_classifier, "classify", _fake_classify)
    stored = _fake_storage(monkeypatch)

    resp = client.post(
        "/identify/photo",
        files={"file": ("bird.jpg", io.BytesIO(make_image()), "image/jpeg")},
    )

    assert resp.status_code == 200
    assert resp.json()["photo_url"] is None
    assert stored == {}


def test_identify_with_store_but_no_storage_still_identifies(client, monkeypatch):
    # Default test settings have no Supabase — the import should still get
    # its candidates, just without a photo to attach.
    monkeypatch.setattr(bioclip_classifier, "classify", _fake_classify)

    resp = client.post(
        "/identify/photo",
        files={"file": ("bird.jpg", io.BytesIO(make_image()), "image/jpeg")},
        data={"store": "true"},
    )

    assert resp.status_code == 200
    assert resp.json()["candidates"]
    assert resp.json()["photo_url"] is None


def test_heic_with_no_content_type_is_accepted_by_extension(client, monkeypatch):
    # Browsers on Windows often send .heic files as application/octet-stream.
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buf, format="HEIF")
    monkeypatch.setattr(bioclip_classifier, "classify", _fake_classify)
    stored = _fake_storage(monkeypatch)

    resp = client.post(
        "/identify/photo",
        files={"file": ("IMG_0001.HEIC", io.BytesIO(buf.getvalue()), "application/octet-stream")},
        data={"store": "true"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["photo_url"].endswith(".jpg")
    assert stored["content_type"] == "image/jpeg"  # HEIC stored as JPEG for non-Safari browsers


def test_unknown_octet_stream_is_still_rejected(client):
    resp = client.post(
        "/identify/photo",
        files={"file": ("notes.bin", io.BytesIO(b"hello"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def _log(client, user_id, batch_id, scientific_name="Cardinalis cardinalis"):
    resp = client.post(
        "/observations",
        json={
            "user_id": user_id,
            "species": {"scientific_name": scientific_name, "common_name": "x"},
            "observed_at": "2026-05-30T19:24:10",
            "source": "manual",
            "status": "logged",
            "import_batch_id": batch_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_import_batch_id_round_trips(client):
    obs = _log(client, "u1", "batch-a")
    assert obs["import_batch_id"] == "batch-a"
    assert client.get(f"/observations/{obs['id']}").json()["import_batch_id"] == "batch-a"


def test_undo_import_deletes_only_that_users_batch(client):
    _log(client, "u1", "batch-a")
    _log(client, "u1", "batch-a", "Turdus migratorius")
    keep_other_batch = _log(client, "u1", "batch-b")
    keep_wizard = _log(client, "u1", None)
    keep_other_user = _log(client, "u2", "batch-a")  # same id, different user

    resp = client.delete("/users/u1/imports/batch-a")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2}
    remaining = {o["id"] for o in client.get("/users/u1/observations").json()}
    assert remaining == {keep_other_batch["id"], keep_wizard["id"]}
    assert client.get(f"/observations/{keep_other_user['id']}").status_code == 200


def test_undo_unknown_import_deletes_nothing(client):
    _log(client, "u1", "batch-a")
    assert client.delete("/users/u1/imports/nope").json() == {"deleted": 0}
