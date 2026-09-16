def test_describe_names_a_species_and_ranks_it_first(client):
    resp = client.post("/identify/describe", json={"text": "I saw a Blue Jay in my backyard"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["identification_id"]
    candidates = body["candidates"]
    assert len(candidates) == 6
    codes = [c["species_code"] for c in candidates]
    assert "blujay" in codes
    assert len(set(codes)) == 6  # no duplicates

    top = max(candidates, key=lambda c: c["confidence"])
    assert top["species_code"] == "blujay"


def test_select_correct_candidate_is_graded_correct(client):
    described = client.post(
        "/identify/describe", json={"text": "definitely a Blue Jay"}
    ).json()

    resp = client.post(
        f"/identify/{described['identification_id']}/select",
        json={"species_code": "blujay"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["outcome"] == "correct"
    assert body["is_match"] is True
    assert body["chosen_species"]["species_code"] == "blujay"


def test_select_wrong_candidate_is_graded_incorrect_but_still_recorded(client):
    described = client.post(
        "/identify/describe", json={"text": "definitely a Blue Jay"}
    ).json()
    other_code = next(
        c["species_code"]
        for c in described["candidates"]
        if c["species_code"] != "blujay"
    )

    resp = client.post(
        f"/identify/{described['identification_id']}/select",
        json={"species_code": other_code},
    )
    body = resp.json()
    assert body["outcome"] == "incorrect"
    assert body["is_match"] is False
    assert body["chosen_species"]["species_code"] == other_code


def test_generic_description_returns_suggestions_with_no_known_target(client):
    resp = client.post(
        "/identify/describe",
        json={
            "text": "small brown streaky bird with a thin beak near the reeds",
            "hints": {"size": "small", "color": "brown", "habitat": "wetland"},
        },
    )
    body = resp.json()
    candidates = body["candidates"]
    assert len(candidates) == 6
    # no confidence should claim near-certainty when we don't actually know
    assert all(c["confidence"] < 0.7 for c in candidates)

    picked_code = candidates[0]["species_code"]
    select = client.post(
        f"/identify/{body['identification_id']}/select",
        json={"species_code": picked_code},
    ).json()
    assert select["outcome"] == "unconfirmed"
    assert select["is_match"] is None
    assert select["chosen_species"]["species_code"] == picked_code


def test_select_rejecting_all_candidates_records_no_chosen_species(client):
    described = client.post(
        "/identify/describe", json={"text": "definitely a Blue Jay"}
    ).json()

    resp = client.post(
        f"/identify/{described['identification_id']}/select",
        json={"species_code": None},
    )
    body = resp.json()
    assert body["chosen_species"] is None
    assert body["outcome"] == "incorrect"  # rejected the named target


def test_select_on_unknown_identification_is_404(client):
    resp = client.post("/identify/does-not-exist/select", json={"species_code": "blujay"})
    assert resp.status_code == 404


def test_full_wizard_confirms_species_and_logs_field_notes(client):
    described = client.post(
        "/identify/describe", json={"text": "I saw a Blue Jay"}
    ).json()
    identification_id = described["identification_id"]
    client.post(
        f"/identify/{identification_id}/select", json={"species_code": "blujay"}
    )

    created = client.post(
        "/observations",
        json={
            "user_id": "u1",
            "species": {
                "common_name": "Blue Jay",
                "scientific_name": "Cyanocitta cristata",
            },
            "identification_id": identification_id,
            "observed_at": "2026-05-01T08:00:00+00:00",
            "location_name": "Discovery Park, Seattle",
            "sex": "male",
            "life_stage": "adult",
            "notes": "Loud call, perched in a cedar.",
            "source": "manual",
            "status": "logged",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["identification_id"] == identification_id
    assert body["location_name"] == "Discovery Park, Seattle"
    assert body["sex"] == "male"
    assert body["life_stage"] == "adult"
    assert body["status"] == "logged"

    life_list = client.get("/users/u1/life-list").json()
    assert any(e["species"]["common_name"] == "Blue Jay" for e in life_list)
