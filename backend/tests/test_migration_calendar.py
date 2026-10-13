"""Migration calendar — docs/features/migration-calendar.md.

Pattern rules are tested with synthetic weekly curves; the endpoints run
against a fake iNaturalist DAO (offline-tests rule) and a fresh in-memory repo.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.dao.migration_repo import InMemoryMigrationRepo
from app.services import migration as migration_service
from app.services import migration_patterns as patterns

# ---- pattern rules --------------------------------------------------------


def _curve(present_weeks, peak_weeks=(), base=20, peak=60, total=1000):
    """Weekly counts (1-based week numbers) against a flat effort total."""
    counts = {w: (peak if w in peak_weeks else base) for w in present_weeks}
    totals = {w: total for w in range(1, 53)}
    folded = patterns.fold_weeks(counts)
    relative = patterns.relative_weekly(folded, patterns.fold_weeks(totals))
    return folded, relative


def test_year_round_species_is_resident():
    counts, rel = _curve(range(1, 53))
    assert patterns.classify(counts, rel) == "resident"


def test_spring_and_fall_only_is_passage():
    # Blackpoll Warbler's real shape near Raleigh: weeks 18–21 and 40–45.
    counts, rel = _curve([18, 19, 20, 21, 40, 41, 42, 43, 44, 45], peak_weeks=[19, 42])
    assert patterns.classify(counts, rel) == "passage"


def test_october_to_april_wrapping_new_year_is_winter():
    counts, rel = _curve(list(range(42, 53)) + list(range(1, 18)))
    assert patterns.classify(counts, rel) == "winter"


def test_april_to_october_is_summer():
    counts, rel = _curve(range(15, 42))
    assert patterns.classify(counts, rel) == "summer"


def test_southern_hemisphere_swaps_seasons():
    counts, rel = _curve(list(range(42, 53)) + list(range(1, 18)))  # present in the southern summer
    assert patterns.classify(counts, rel, southern=True) == "summer"


def test_too_few_observations_is_irregular():
    counts, rel = _curve([20, 40], base=2)
    assert patterns.classify(counts, rel) == "irregular"


def test_effort_normalization_uses_share_not_raw_counts():
    # Same raw count in two weeks, but half the birders in the second: the
    # species is twice as common there.
    rel = patterns.relative_weekly(
        patterns.fold_weeks({10: 10, 30: 10}), patterns.fold_weeks({w: 2000 for w in range(1, 53)} | {30: 1000})
    )
    assert rel[29] > rel[9]


def test_week_53_folds_into_52():
    assert patterns.fold_weeks({52: 3, 53: 2})[51] == 5


def test_movement_arriving_peak_leaving():
    counts, rel = _curve(range(15, 30), peak_weeks=[22, 23, 24])
    assert patterns.movement(rel, 16) == "arriving"
    assert patterns.movement(rel, 23) == "peak"
    assert patterns.movement(rel, 28) == "leaving"
    assert patterns.movement(rel, 45) is None


def test_one_rare_bird_everyone_photographed_is_irregular():
    # Kirtland's Warbler near Raleigh, from real data: 17 records, 13 in one week.
    counts = patterns.fold_weeks({39: 4, 40: 13})
    rel = patterns.relative_weekly(counts, patterns.fold_weeks({w: 2000 for w in range(1, 53)}))
    assert patterns.classify(counts, rel) == "irregular"


def test_minimum_observations_scale_with_the_area():
    assert patterns.min_obs_for(2_000) == 10  # data-poor: the floor
    assert patterns.min_obs_for(101_203) == 20  # Raleigh
    counts, rel = _curve(range(15, 42), base=1)  # 27 records of a "summer visitor"
    assert patterns.classify(counts, rel, min_obs=10) == "summer"
    assert patterns.classify(counts, rel, min_obs=30) == "irregular"


def test_summer_visitor_is_arriving_then_settled_then_leaving():
    # Real-data regression: slope-based rules called nesting Purple Martins
    # "leaving" in May. A summer visitor in mid-season is just here.
    counts, rel = _curve(range(15, 40), peak_weeks=[17, 18])  # spring photo spike, then steady
    assert patterns.movement(rel, 16, "summer") == "arriving"
    assert patterns.movement(rel, 26, "summer") is None
    assert patterns.movement(rel, 38, "summer") == "leaving"
    assert patterns.movement(rel, 45, "summer") is None


def test_cell_for_snaps_to_half_degree_grid():
    cell_id, clat, clng = migration_service.cell_for(35.78, -78.64)
    assert cell_id == "35.5:-79"
    assert (clat, clng) == (35.75, -78.75)


# ---- endpoints ------------------------------------------------------------

# Fake iNaturalist: a resident cardinal, a passage warbler, a summer swift.
_SPECIES = {
    "Cardinalis cardinalis": ("Northern Cardinal", range(1, 54)),
    "Setophaga striata": ("Blackpoll Warbler", [18, 19, 20, 21, 40, 41, 42, 43, 44]),
    "Chaetura pelagica": ("Chimney Swift", range(15, 42)),
}


@pytest.fixture()
def fake_cell(monkeypatch):
    repo = InMemoryMigrationRepo()
    monkeypatch.setattr("app.services.migration.migration_repo", repo)
    monkeypatch.setattr(migration_service, "REQUEST_SPACING_S", 0)
    calls = {"species": 0}

    async def count_weekly_observations(lat, lng, radius_km, week):
        return 1000

    async def get_weekly_species_counts(lat, lng, radius_km, week):
        calls["species"] += 1
        return [
            {"count": 30, "taxon": {"name": sci, "preferred_common_name": common, "id": i, "rank": "species"}}
            for i, (sci, (common, weeks)) in enumerate(_SPECIES.items())
            if week in weeks
        ]

    monkeypatch.setattr("app.dao.inaturalist.count_weekly_observations", count_weekly_observations)
    monkeypatch.setattr("app.dao.inaturalist.get_weekly_species_counts", get_weekly_species_counts)
    return repo, calls


def test_first_request_is_202_then_built_calendar_is_served(client, fake_cell):
    _, calls = fake_cell

    first = client.get("/migration/calendar", params={"lat": 35.78, "lng": -78.64})
    assert first.status_code == 202
    assert first.json() == {"cell_id": "35.5:-79", "status": "building"}
    assert calls["species"] == 53  # TestClient runs the background build right after responding

    second = client.get("/migration/calendar", params={"lat": 35.9, "lng": -78.9})  # same cell
    assert second.status_code == 200
    body = second.json()
    patterns_by_name = {s["common_name"]: s["pattern"] for s in body["species"]}
    assert patterns_by_name == {"Northern Cardinal": "resident", "Blackpoll Warbler": "passage", "Chimney Swift": "summer"}
    assert all(len(s["weekly"]) == 52 for s in body["species"])
    assert body["species"][0]["pattern"] == "passage"  # migrants sort before residents
    assert body["data_quality"] == "good"
    assert calls["species"] == 53  # cached — not rebuilt


def test_now_lists_migrants_only_and_marks_life_list(client, fake_cell):
    client.get("/migration/now", params={"lat": 35.78, "lng": -78.64})  # triggers the build
    client.post("/observations", json={
        "user_id": "u1", "species": {"scientific_name": "Setophaga striata", "common_name": "Blackpoll Warbler"},
        "observed_at": "2025-05-01T08:00:00+00:00", "source": "manual", "status": "logged",
    })

    resp = client.get("/migration/now", params={"lat": 35.78, "lng": -78.64, "week": 19, "user_id": "u1"})

    assert resp.status_code == 200
    body = resp.json()
    everyone = body["arriving"] + body["peak"] + body["leaving"]
    names = {s["common_name"] for s in everyone}
    assert "Blackpoll Warbler" in names
    assert "Northern Cardinal" not in names  # residents aren't migrating
    warbler = next(s for s in everyone if s["common_name"] == "Blackpoll Warbler")
    assert warbler["on_life_list"] is True


def test_failed_build_is_retried_on_next_visit(client, fake_cell, monkeypatch):
    repo, calls = fake_cell
    from app.dao import inaturalist

    real_fake = inaturalist.count_weekly_observations
    state = {"down": True}

    async def flaky(lat, lng, radius_km, week):
        if state["down"]:
            raise RuntimeError("iNaturalist down")
        return await real_fake(lat, lng, radius_km, week)

    monkeypatch.setattr("app.dao.inaturalist.count_weekly_observations", flaky)  # wraps the fake_cell fake

    assert client.get("/migration/calendar", params={"lat": 35.78, "lng": -78.64}).status_code == 202
    assert asyncio.run(repo.get_calendar("35.5:-79"))["status"] == "failed"

    state["down"] = False
    assert client.get("/migration/calendar", params={"lat": 35.78, "lng": -78.64}).status_code == 202
    assert asyncio.run(repo.get_calendar("35.5:-79"))["status"] == "ready"
    assert client.get("/migration/calendar", params={"lat": 35.78, "lng": -78.64}).status_code == 200


def test_claim_build_refuses_a_running_build_but_takes_over_an_abandoned_one():
    repo = InMemoryMigrationRepo()
    assert asyncio.run(repo.claim_build("c", 0.25, 0.25, 40)) is True
    assert asyncio.run(repo.claim_build("c", 0.25, 0.25, 40)) is False  # someone is already building
    repo._calendars["c"]["updated_at"] = datetime.now(timezone.utc) - timedelta(minutes=11)
    assert asyncio.run(repo.claim_build("c", 0.25, 0.25, 40)) is True


def test_stale_calendar_is_served_while_refreshing(client, fake_cell):
    repo, calls = fake_cell
    client.get("/migration/calendar", params={"lat": 35.78, "lng": -78.64})
    repo._calendars["35.5:-79"]["built_at"] -= timedelta(days=91)

    resp = client.get("/migration/calendar", params={"lat": 35.78, "lng": -78.64})

    assert resp.status_code == 200  # old data, not a 202
    assert resp.json()["refreshing"] is True
    assert calls["species"] == 106  # and a rebuild ran in the background
