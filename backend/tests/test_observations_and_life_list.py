OBS = {
    "user_id": "u1",
    "lat": 47.6,
    "lng": -122.33,
    "observed_at": "2026-05-01T08:00:00+00:00",
    "source": "manual",
    "species": {"scientific_name": "Corvus corax", "common_name": "Common Raven"},
}


def test_log_list_and_fetch_observation(client):
    created = client.post("/observations", json=OBS)
    assert created.status_code == 201
    obs_id = created.json()["id"]
    assert obs_id

    listed = client.get("/users/u1/observations")
    assert listed.status_code == 200
    assert [o["id"] for o in listed.json()] == [obs_id]

    fetched = client.get(f"/observations/{obs_id}")
    assert fetched.status_code == 200
    assert fetched.json()["species"]["common_name"] == "Common Raven"

    assert client.get("/observations/does-not-exist").status_code == 404


def test_list_is_newest_first_and_scoped_by_user(client):
    client.post("/observations", json={**OBS, "observed_at": "2026-01-01T00:00:00+00:00"})
    client.post("/observations", json={**OBS, "observed_at": "2026-06-01T00:00:00+00:00"})
    client.post("/observations", json={**OBS, "user_id": "u2"})

    rows = client.get("/users/u1/observations").json()
    assert len(rows) == 2
    assert rows[0]["observed_at"] > rows[1]["observed_at"]


def test_life_list_dedupes_species_to_earliest_sighting(client):
    client.post("/observations", json={**OBS, "observed_at": "2026-05-01T00:00:00+00:00"})
    client.post("/observations", json={**OBS, "observed_at": "2026-03-01T00:00:00+00:00"})
    client.post(
        "/observations",
        json={
            **OBS,
            "observed_at": "2026-04-01T00:00:00+00:00",
            "species": {"scientific_name": "Cyanocitta stelleri"},
        },
    )

    life_list = client.get("/users/u1/life-list").json()
    by_name = {e["species"]["scientific_name"]: e for e in life_list}
    assert set(by_name) == {"Corvus corax", "Cyanocitta stelleri"}
    assert by_name["Corvus corax"]["first_observed_at"].startswith("2026-03-01")
