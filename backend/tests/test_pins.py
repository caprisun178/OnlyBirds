"""Pinned Birds — `app/dao/pin_repo.py`, `app/services/pins.py`,
`app/routers/pins.py`. Everything here is our own data (no external API —
see docs/features/pinned-birds.md), so these run against the `client`
fixture's isolated in-memory repos, no mocking needed beyond that.

The `client` fixture mocks `ebird.get_hotspots_near` to return `[]` (see its
docstring in conftest.py), so `region_for_point()` always resolves to
`"world"` for any observation logged over HTTP in these tests. `"world"`
matches every pin's region, which is enough to test the end-to-end
wiring (pin -> log -> notify) honestly, but not the actual region-*prefix*
matching logic — that's tested directly against
`app.services.pins.evaluate_pins()` with explicit region strings instead,
in the second half of this file.
"""

import asyncio
from datetime import datetime

from app.models.observation import Observation
from app.models.species import SpeciesRef
from app.services.pins import evaluate_pins


def _log(client, user_id, scientific_name, common_name, lat, lng):
    resp = client.post(
        "/observations",
        json={
            "user_id": user_id,
            "species": {"scientific_name": scientific_name, "common_name": common_name},
            "observed_at": "2026-10-01T08:00:00+00:00",
            "lat": lat,
            "lng": lng,
            "source": "manual",
            "status": "logged",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_pin_defaults_region_to_the_users_default_region(client):
    client.post("/users", json={"auth_provider_id": "u1"})
    client.patch("/users/u1", json={"default_region": "US-WA"})

    resp = client.post(
        "/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "common_name": "Snowy Owl"}
    )
    assert resp.status_code == 201
    assert resp.json()["region"] == "US-WA"


def test_pin_accepts_an_explicit_region_override(client):
    resp = client.post(
        "/users/u1/pins",
        json={"scientific_name": "Bubo scandiacus", "common_name": "Snowy Owl", "region": "US-WA-033"},
    )
    assert resp.status_code == 201
    assert resp.json()["region"] == "US-WA-033"


def test_pinning_a_species_already_on_the_life_list_is_rejected(client):
    _log(client, "u1", "Cardinalis cardinalis", "Northern Cardinal", 36.1, -80.3)

    resp = client.post("/users/u1/pins", json={"scientific_name": "Cardinalis cardinalis", "region": "world"})

    assert resp.status_code == 409


def test_pinning_the_same_species_twice_updates_the_region_not_a_duplicate(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "US-WA"})
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "US-OR"})

    pins = client.get("/users/u1/pins").json()
    assert len(pins) == 1
    assert pins[0]["region"] == "US-OR"


def test_patch_pin_region(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "US-WA"})

    resp = client.patch("/users/u1/pins/Bubo scandiacus", json={"region": "US"})

    assert resp.status_code == 200
    assert resp.json()["region"] == "US"


def test_patch_nonexistent_pin_404s(client):
    resp = client.patch("/users/u1/pins/Bubo scandiacus", json={"region": "US"})
    assert resp.status_code == 404


def test_unpin(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "US-WA"})

    resp = client.delete("/users/u1/pins/Bubo scandiacus")
    assert resp.status_code == 204
    assert client.get("/users/u1/pins").json() == []


def test_unpin_nonexistent_pin_404s(client):
    resp = client.delete("/users/u1/pins/Bubo scandiacus")
    assert resp.status_code == 404


# ---- End-to-end wiring: pin -> log -> notify (region="world" throughout,
# since that's what the mocked lookup always resolves to — see module
# docstring) ------------------------------------------------------------


def test_logging_a_pinned_species_notifies_the_pinning_user(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "world"})

    _log(client, "u2", "Bubo scandiacus", "Snowy Owl", 47.6, -122.3)

    notifications = client.get("/users/u1/notifications").json()
    assert len(notifications) == 1
    assert notifications[0]["kind"] == "pin_hit"
    assert notifications[0]["payload"]["species"] == "Bubo scandiacus"
    assert notifications[0]["read_at"] is None


def test_reporter_is_never_notified_of_their_own_sighting(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "world"})

    _log(client, "u1", "Bubo scandiacus", "Snowy Owl", 47.6, -122.3)

    assert client.get("/users/u1/notifications").json() == []


def test_logging_a_different_species_does_not_notify(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "world"})

    _log(client, "u2", "Cardinalis cardinalis", "Northern Cardinal", 47.6, -122.3)

    assert client.get("/users/u1/notifications").json() == []


def test_notifications_feed_unread_filter_and_mark_read(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "world"})
    _log(client, "u2", "Bubo scandiacus", "Snowy Owl", 47.6, -122.3)

    assert len(client.get("/users/u1/notifications?unread=true").json()) == 1

    resp = client.post("/users/u1/notifications/read")
    assert resp.status_code == 200
    assert resp.json()["marked_read"] == 1

    assert client.get("/users/u1/notifications?unread=true").json() == []
    assert len(client.get("/users/u1/notifications").json()) == 1  # still in the feed, just read


# ---- Region-prefix matching and dedup, tested directly against the
# service (explicit regions — not at the mercy of the mocked eBird lookup)
# ---------------------------------------------------------------------------


def _observation(user_id, scientific_name, common_name, region, observed_at="2026-10-01T08:00:00+00:00"):
    return Observation(
        id="obs-1",
        user_id=user_id,
        species=SpeciesRef(scientific_name=scientific_name, common_name=common_name),
        lat=47.6,
        lng=-122.3,
        observed_at=datetime.fromisoformat(observed_at),
        source="manual",
        region=region,
        status="logged",
    )


def test_evaluate_pins_matches_a_narrower_observation_region_inside_a_wider_pin(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "US-WA"})

    notified = asyncio.run(
        evaluate_pins(_observation("u2", "Bubo scandiacus", "Snowy Owl", region="US-WA-033"))
    )

    assert notified == ["u1"]


def test_evaluate_pins_does_not_match_a_sighting_outside_the_pinned_region(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "US-WA"})

    notified = asyncio.run(
        evaluate_pins(_observation("u2", "Bubo scandiacus", "Snowy Owl", region="US-OR"))
    )

    assert notified == []


def test_evaluate_pins_a_world_pin_matches_any_region(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "world"})

    notified = asyncio.run(
        evaluate_pins(_observation("u2", "Bubo scandiacus", "Snowy Owl", region="US-OR-051"))
    )

    assert notified == ["u1"]


def test_evaluate_pins_dedupes_repeat_sightings_the_same_day(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "world"})

    first = asyncio.run(evaluate_pins(_observation("u2", "Bubo scandiacus", "Snowy Owl", region="US-WA")))
    second = asyncio.run(evaluate_pins(_observation("u3", "Bubo scandiacus", "Snowy Owl", region="US-WA")))

    assert first == ["u1"]
    assert second == []  # same (user, species, region, day) — collapsed, not a second notification
    assert len(client.get("/users/u1/notifications").json()) == 1


def test_evaluate_pins_a_different_day_is_not_deduped(client):
    client.post("/users/u1/pins", json={"scientific_name": "Bubo scandiacus", "region": "world"})

    asyncio.run(evaluate_pins(_observation("u2", "Bubo scandiacus", "Snowy Owl", region="US-WA", observed_at="2026-10-01T08:00:00+00:00")))
    second = asyncio.run(
        evaluate_pins(_observation("u2", "Bubo scandiacus", "Snowy Owl", region="US-WA", observed_at="2026-10-02T08:00:00+00:00"))
    )

    assert second == ["u1"]
    assert len(client.get("/users/u1/notifications").json()) == 2
