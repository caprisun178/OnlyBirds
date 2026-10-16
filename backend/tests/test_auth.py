"""Offline tests for sign-in and the auth checks on user-scoped endpoints.

Google is never called: `google_auth.verify_id_token` is monkeypatched.
`client` signs requests in automatically (see conftest.py); `anon_client`
doesn't, so these use it plus explicit tokens to control who's calling.
"""

import pytest

from app.config import get_settings
from app.dao import google_auth
from app.services import auth as auth_service
from app.services.auth import create_session_token, verify_session_token

GOOGLE_CLAIMS = {
    "sub": "1234567890",
    "email": "birder@example.com",
    "name": "Bea Birder",
    "picture": "https://lh3.googleusercontent.com/a/photo.jpg",
}


def _bearer(user_id: str) -> dict:
    token, _ = create_session_token(user_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def fake_google(monkeypatch):
    async def _verify(id_token, client_id):
        if id_token != "good-google-token":
            raise google_auth.InvalidGoogleToken("Google rejected the token")
        return {**GOOGLE_CLAIMS, "aud": client_id}

    monkeypatch.setattr("app.dao.google_auth.verify_id_token", _verify)


# ---- sign-in ----------------------------------------------------------------


def test_config_exposes_client_id(anon_client):
    assert anon_client.get("/auth/config").json() == {"google_client_id": get_settings().google_client_id}


def test_config_is_null_when_unconfigured(anon_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "session_secret", None)
    assert anon_client.get("/auth/config").json() == {"google_client_id": None}


def test_google_sign_in_creates_user_and_session(anon_client, fake_google):
    r = anon_client.post("/auth/google", json={"credential": "good-google-token"})

    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Bea Birder"
    assert body["profile"]["id"] == "google:1234567890"
    assert body["profile"]["avatar_url"] == GOOGLE_CLAIMS["picture"]

    me = anon_client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == "google:1234567890"


def test_sign_in_again_keeps_an_uploaded_avatar(anon_client, fake_google):
    anon_client.post("/auth/google", json={"credential": "good-google-token"})
    anon_client.patch(
        "/users/google:1234567890",
        json={"avatar_url": "https://example.com/mine.jpg"},
        headers=_bearer("google:1234567890"),
    )

    r = anon_client.post("/auth/google", json={"credential": "good-google-token"})

    assert r.json()["profile"]["avatar_url"] == "https://example.com/mine.jpg"


def test_bad_google_token_is_401(anon_client, fake_google):
    r = anon_client.post("/auth/google", json={"credential": "forged"})
    assert r.status_code == 401


def test_sign_in_unconfigured_is_503(anon_client, fake_google, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", None)
    r = anon_client.post("/auth/google", json={"credential": "good-google-token"})
    assert r.status_code == 503


def test_me_signed_out_is_401(anon_client):
    assert anon_client.get("/auth/me").status_code == 401


# ---- session tokens ---------------------------------------------------------


def test_session_token_round_trips(client):
    token, _ = create_session_token("u1")
    assert verify_session_token(token) == "u1"


def test_tampered_session_token_is_rejected(client):
    # u2's payload with u1's signature — i.e. editing the user id in a token.
    _, signature = create_session_token("u1")[0].split(".")
    forged_payload, _ = create_session_token("u2")[0].split(".")
    with pytest.raises(auth_service.InvalidSession):
        verify_session_token(f"{forged_payload}.{signature}")


def test_expired_session_token_is_rejected(client):
    token, expires_at = create_session_token("u1")
    with pytest.raises(auth_service.InvalidSession):
        verify_session_token(token, now=expires_at.timestamp() + 1)


def test_token_signed_with_another_secret_is_rejected(client, monkeypatch):
    token, _ = create_session_token("u1")
    monkeypatch.setattr(get_settings(), "session_secret", "rotated")
    with pytest.raises(auth_service.InvalidSession):
        verify_session_token(token)


# ---- enforcement on user-scoped endpoints -----------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/users/u1/pins"),
        ("get", "/users/u1/observations"),
        ("get", "/users/u1/life-list"),
        ("get", "/users/u1/notifications"),
        ("get", "/users/u1/stickers"),
    ],
)
def test_user_endpoints_need_sign_in(anon_client, method, path):
    assert getattr(anon_client, method)(path).status_code == 401


@pytest.mark.parametrize(
    "path",
    ["/users/u1/pins", "/users/u1/observations", "/users/u1/life-list", "/users/u1/notifications"],
)
def test_user_endpoints_reject_other_users(anon_client, path):
    assert anon_client.get(path, headers=_bearer("u2")).status_code == 403


def test_garbage_token_counts_as_signed_out(anon_client):
    r = anon_client.get("/users/u1/pins", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_cannot_log_an_observation_as_someone_else(anon_client):
    payload = {
        "user_id": "u1",
        "lat": 35.0,
        "lng": -78.0,
        "observed_at": "2026-09-01T12:00:00Z",
        "species": {"scientific_name": "Cardinalis cardinalis"},
    }
    assert anon_client.post("/observations", json=payload).status_code == 401
    assert anon_client.post("/observations", json=payload, headers=_bearer("u2")).status_code == 403
    assert anon_client.post("/observations", json=payload, headers=_bearer("u1")).status_code == 201


def test_cannot_edit_someone_elses_observation(anon_client):
    created = anon_client.post(
        "/observations",
        json={
            "user_id": "u1",
            "lat": 35.0,
            "lng": -78.0,
            "observed_at": "2026-09-01T12:00:00Z",
            "species": {"scientific_name": "Cardinalis cardinalis"},
        },
        headers=_bearer("u1"),
    ).json()

    r = anon_client.patch(f"/observations/{created['id']}", json={"notes": "mine now"}, headers=_bearer("u2"))

    assert r.status_code == 403


def test_cannot_patch_someone_elses_profile(anon_client):
    anon_client.post("/users", json={"auth_provider_id": "u1"}, headers=_bearer("u1"))
    r = anon_client.patch("/users/u1", json={"default_region": "US-NC"}, headers=_bearer("u2"))
    assert r.status_code == 403


def test_public_profile_needs_no_sign_in(anon_client):
    anon_client.post("/users", json={"auth_provider_id": "u1", "username": "hawkeye"}, headers=_bearer("u1"))
    assert anon_client.get("/users/hawkeye").status_code == 200
    assert anon_client.get("/users/by-id/u1").status_code == 200


def test_photo_upload_needs_sign_in(anon_client):
    r = anon_client.post("/uploads/photo", files={"file": ("a.jpg", b"x", "image/jpeg")})
    assert r.status_code == 401
