"""Offline tests for the user profile endpoints (in-memory repo, no network)."""


def test_create_and_get_profile(client):
    r = client.post("/users", json={"auth_provider_id": "u1", "username": "hawkeye"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "u1"
    assert body["username"] == "hawkeye"
    assert body["default_region"] == "world"
    assert body["life_list_total"] == 0

    r = client.get("/users/hawkeye")
    assert r.status_code == 200
    assert r.json()["id"] == "u1"


def test_get_unknown_user_is_404(client):
    assert client.get("/users/nobody").status_code == 404


def test_get_profile_by_id(client):
    client.post("/users", json={"auth_provider_id": "u1", "username": "hawkeye"})

    r = client.get("/users/by-id/u1")

    assert r.status_code == 200
    assert r.json()["id"] == "u1"
    assert r.json()["username"] == "hawkeye"


def test_get_profile_by_id_unknown_user_is_404(client):
    assert client.get("/users/by-id/ghost").status_code == 404


def test_get_profile_by_id_works_even_without_a_username(client):
    # auth_provider_id is always present; username is optional (UserCreate) —
    # the by-id lookup must not depend on one existing, unlike GET /users/{username}.
    client.post("/users", json={"auth_provider_id": "u1"})

    r = client.get("/users/by-id/u1")

    assert r.status_code == 200
    assert r.json()["username"] is None


def test_patch_default_region(client):
    client.post("/users", json={"auth_provider_id": "u1", "username": "hawkeye"})
    r = client.patch("/users/u1", json={"default_region": "US-NC"})
    assert r.status_code == 200
    assert r.json()["default_region"] == "US-NC"
    assert client.get("/users/hawkeye").json()["default_region"] == "US-NC"


def test_patch_unknown_user_is_404(client):
    r = client.patch("/users/ghost", json={"default_region": "US-NC"})
    assert r.status_code == 404


def test_username_taken_is_409(client):
    client.post("/users", json={"auth_provider_id": "u1", "username": "hawkeye"})
    r = client.post("/users", json={"auth_provider_id": "u2", "username": "hawkeye"})
    assert r.status_code == 409


def test_invalid_username_is_422(client):
    r = client.post("/users", json={"auth_provider_id": "u1", "username": "a b"})
    assert r.status_code == 422


def test_profile_counts_life_list(client):
    client.post("/users", json={"auth_provider_id": "u1", "username": "hawkeye"})
    client.post(
        "/observations",
        json={
            "user_id": "u1",
            "lat": 35.0,
            "lng": -78.0,
            "observed_at": "2026-09-01T12:00:00Z",
            "species": {"scientific_name": "Cardinalis cardinalis"},
        },
    )
    assert client.get("/users/hawkeye").json()["life_list_total"] == 1