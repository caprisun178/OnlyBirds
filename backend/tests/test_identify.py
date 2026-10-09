import io


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


def test_generic_description_covers_non_songbird_categories(client):
    # Regression: the reference set used to be songbirds only, so a category
    # like owls had zero entries and could never be suggested.
    resp = client.post("/identify/describe", json={"text": "brown owl"})
    names = [c["common_name"] for c in resp.json()["candidates"]]
    assert sum("Owl" in name for name in names) >= 3


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


def test_default_sense_is_sight_and_never_fetches_audio(client, monkeypatch):
    from app.dao import commons

    calls = []

    async def fake_search_audio(query):
        calls.append(query)
        return None

    monkeypatch.setattr(commons, "search_audio", fake_search_audio)

    resp = client.post("/identify/describe", json={"text": "I saw a Blue Jay"})
    body = resp.json()
    assert body["sense"] == "sight"
    assert all(c["audio_url"] is None and c["audio_attribution"] is None for c in body["candidates"])
    assert calls == []  # sight mode never calls the audio lookup at all


def test_sound_sense_fetches_audio_for_every_candidate(client, monkeypatch):
    from app.dao import commons

    async def fake_search_audio(query):
        return {"media_url": f"https://example.com/{query.replace(' ', '_')}.mp3", "artist": "Test Recorder"}

    monkeypatch.setattr(commons, "search_audio", fake_search_audio)

    resp = client.post("/identify/describe", json={"text": "I heard a Blue Jay", "sense": "sound"})
    body = resp.json()
    assert body["sense"] == "sound"
    assert len(body["candidates"]) == 6
    assert all(c["audio_url"] and c["audio_url"].endswith(".mp3") for c in body["candidates"])
    assert all("Test Recorder" in c["audio_attribution"] for c in body["candidates"])


def test_sound_sense_candidate_with_no_recording_has_null_audio(client, monkeypatch):
    from app.dao import commons

    async def fake_search_audio(query):
        return None

    monkeypatch.setattr(commons, "search_audio", fake_search_audio)

    resp = client.post("/identify/describe", json={"text": "I heard a Blue Jay", "sense": "sound"})
    body = resp.json()
    assert all(c["audio_url"] is None for c in body["candidates"])


def _fake_classification():
    return [
        {"scientific_name": "Cardinalis cardinalis", "common_name": "Northern Cardinal", "species_code": "norcar", "confidence": 0.79},
        {"scientific_name": "Cardinalis sinuatus", "common_name": "Pyrrhuloxia", "species_code": "pyrrhu", "confidence": 0.20},
    ]


def test_photo_identify_returns_ranked_candidates(client, monkeypatch):
    # Never run real BioCLIP inference in a test — offline-tests rule
    # (docs/ebird-api.md), and a real model load/run is slow besides.
    from app.dao import bioclip_classifier

    monkeypatch.setattr(
        bioclip_classifier, "classify", lambda image_bytes, top_k=6, candidates=None: _fake_classification()
    )

    resp = client.post(
        "/identify/photo",
        files={"file": ("bird.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "photo"
    assert body["sense"] == "sight"
    candidates = body["candidates"]
    assert len(candidates) == 2
    assert candidates[0]["species_code"] == "norcar"
    assert candidates[0]["confidence"] == 0.79
    assert all(c["audio_url"] is None for c in candidates)  # a photo is never "sound"


def test_photo_identify_rejects_unsupported_content_type(client):
    resp = client.post(
        "/identify/photo",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


def test_photo_identify_rejects_oversized_file(client, monkeypatch):
    from app.services import uploads as upload_service

    monkeypatch.setattr(upload_service, "MAX_BYTES", 10)
    resp = client.post(
        "/identify/photo",
        files={"file": ("bird.jpg", io.BytesIO(b"x" * 100), "image/jpeg")},
    )
    assert resp.status_code == 400


def test_photo_identify_candidate_can_be_selected(client, monkeypatch):
    from app.dao import bioclip_classifier

    monkeypatch.setattr(
        bioclip_classifier, "classify", lambda image_bytes, top_k=6, candidates=None: _fake_classification()
    )

    identified = client.post(
        "/identify/photo",
        files={"file": ("bird.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
    ).json()

    resp = client.post(
        f"/identify/{identified['identification_id']}/select",
        json={"species_code": "norcar"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # No named target for a photo (unlike describe's "named" path) — grading
    # just trusts whichever candidate the user recognized, same as a generic
    # text description.
    assert body["outcome"] == "unconfirmed"
    assert body["is_match"] is None
    assert body["chosen_species"]["species_code"] == "norcar"


def _stub_region(monkeypatch, region_species_codes, region_code="US-NC-067"):
    """`region_species_codes` is a set of eBird codes — `comName`/`sciName`
    are fabricated from the code since describe-flow's reorder tests never
    read them; photo-flow tests that care about specific names pass their
    own checklist rows directly instead (see `_stub_region_checklist`)."""
    from app.dao import ebird

    async def fake_region_for_point(lat, lng):
        return region_code

    async def fake_get_historic_checklist(region, d):
        return [
            {"speciesCode": code, "comName": f"Species {code}", "sciName": f"Sci {code}"}
            for code in region_species_codes
        ]

    monkeypatch.setattr(ebird, "region_for_point", fake_region_for_point)
    monkeypatch.setattr(ebird, "get_historic_checklist", fake_get_historic_checklist)


def test_photo_identify_passes_regional_checklist_as_candidate_pool(client, monkeypatch):
    # The real failure mode this fixes: the old fixed-label model couldn't
    # help but compete an out-of-region vagrant against the real answer.
    # BioCLIP's pool *is* the candidate set, so scoping it to eBird's real
    # regional checklist means an implausible species never gets a vote at
    # all — confirm identify_photo() builds and passes exactly that pool.
    from app.dao import bioclip_classifier

    _stub_region(monkeypatch, region_species_codes={"grbher3", "squher1"})

    captured = {}

    def fake_classify(image_bytes, top_k=6, candidates=None):
        captured["candidates"] = candidates
        return _fake_classification()

    monkeypatch.setattr(bioclip_classifier, "classify", fake_classify)

    resp = client.post(
        "/identify/photo",
        files={"file": ("bird.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
        data={"lat": "35.9", "lng": "-79.0", "observed_at": "2026-05-01"},
    )
    assert resp.status_code == 200
    assert captured["candidates"] is not None
    codes = {c["species_code"] for c in captured["candidates"]}
    assert codes == {"grbher3", "squher1"}
    # Real names flowed through, not just codes — this is what gets embedded
    # as zero-shot text prompts, so a placeholder would defeat the point.
    assert all(c["common_name"] for c in captured["candidates"])


def test_photo_identify_with_no_location_uses_classifiers_default_pool(client, monkeypatch):
    from app.dao import bioclip_classifier

    captured = {}

    def fake_classify(image_bytes, top_k=6, candidates=None):
        captured["candidates"] = candidates
        return _fake_classification()

    monkeypatch.setattr(bioclip_classifier, "classify", fake_classify)

    resp = client.post(
        "/identify/photo",
        files={"file": ("bird.jpg", io.BytesIO(b"fake-image-bytes"), "image/jpeg")},
    )
    assert resp.status_code == 200
    # No lat/lng/observed_at given -> no regional pool to build; the
    # classifier falls back to its own default pool, not an empty one.
    assert captured["candidates"] is None


def test_describe_generic_reorders_toward_regional_species(client, monkeypatch):
    # "brown owl" matches several owls by keyword/color (see birds.py) with
    # no single named target — the generic, no-ground-truth path this
    # reorder is meant for. No lat/lng on this first call, so it's an
    # unreordered baseline regardless of region stubbing.
    baseline = client.post("/identify/describe", json={"text": "brown owl"}).json()
    all_owl_codes = [c["species_code"] for c in baseline["candidates"]]

    # Pick a real code from this run's own candidates rather than guessing
    # the data file's naming — the point under test is reordering mechanics,
    # not a specific species' exact eBird code.
    target = all_owl_codes[-1]  # whichever ranked last on text score alone
    _stub_region(monkeypatch, region_species_codes={target})

    resp = client.post("/identify/describe", json={
        "text": "brown owl", "lat": 35.9, "lng": -79.0, "observed_at": "2026-05-01",
    })
    codes = [c["species_code"] for c in resp.json()["candidates"]]
    assert codes[0] == target
    assert set(codes) == set(all_owl_codes)  # reordered, nothing dropped or added


def test_describe_named_match_is_never_reordered_by_region(client, monkeypatch):
    # Ground truth from naming the species outright must never be
    # second-guessed by an incomplete regional checklist — see
    # app/services/identify.py#describe_bird()'s target_code is None check.
    _stub_region(monkeypatch, region_species_codes=set())  # Blue Jay confirmed absent from this "region"

    resp = client.post("/identify/describe", json={
        "text": "definitely a Blue Jay", "lat": 35.9, "lng": -79.0, "observed_at": "2026-05-01",
    })
    candidates = resp.json()["candidates"]
    top = max(candidates, key=lambda c: c["confidence"])
    assert top["species_code"] == "blujay"


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
            "observed_at": "2026-05-01T08:00:00+00:00",
            "location_name": "Discovery Park, Seattle",
            "sex": "male",
            "life_stage": "adult",
            "detection_type": "sound",
            "notes": "Loud call, perched in a cedar.",
            "source": "manual",
            "status": "logged",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["location_name"] == "Discovery Park, Seattle"
    assert body["sex"] == "male"
    assert body["life_stage"] == "adult"
    assert body["detection_type"] == "sound"
    assert body["status"] == "logged"

    life_list = client.get("/users/u1/life-list").json()
    assert any(e["species"]["common_name"] == "Blue Jay" for e in life_list)
