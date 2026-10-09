"""Test Your Skill — `app/services/quiz.py`, `app/routers/quiz.py`. Mocks
`region_repo.get_checklist()` (no live eBird calls — docs/ebird-api.md's
offline-tests rule) with a small canned checklist, and
`bird_photos.get_stock_photo`/`bird_audio.get_audio` directly, same as the
original version of this test file.
"""

import asyncio

import pytest

from app.dao.ebird import EBirdConfigError
from app.services import quiz

# 4 corvids + 2 warblers — enough to exercise both the "same family has >=3
# others" distractor path (corvids) and the "too few, fall back to the
# whole pool" path (warblers, only 1 other member).
CHECKLIST = [
    {"code": "blujay", "common_name": "Blue Jay", "scientific_name": "Cyanocitta cristata", "taxon_order": 1, "family_common_name": "Crows, Jays, and Magpies"},
    {"code": "stejay1", "common_name": "Steller's Jay", "scientific_name": "Cyanocitta stelleri", "taxon_order": 2, "family_common_name": "Crows, Jays, and Magpies"},
    {"code": "amecro", "common_name": "American Crow", "scientific_name": "Corvus brachyrhynchos", "taxon_order": 3, "family_common_name": "Crows, Jays, and Magpies"},
    {"code": "comrav", "common_name": "Common Raven", "scientific_name": "Corvus corax", "taxon_order": 4, "family_common_name": "Crows, Jays, and Magpies"},
    {"code": "yelwar", "common_name": "Yellow Warbler", "scientific_name": "Setophaga petechia", "taxon_order": 5, "family_common_name": "New World Warblers"},
    {"code": "wlswar", "common_name": "Wilson's Warbler", "scientific_name": "Cardellina pusilla", "taxon_order": 6, "family_common_name": "New World Warblers"},
]


@pytest.fixture(autouse=True)
def canned_checklist(monkeypatch):
    async def fake_get_checklist(region_code):
        return CHECKLIST

    monkeypatch.setattr(quiz.region_repo, "get_checklist", fake_get_checklist)


@pytest.fixture(autouse=True)
def no_shuffle(monkeypatch):
    """Neutralizes get_question()'s random.shuffle() so species are tried in
    CHECKLIST's own fixed order — see the original version of this fixture
    for why that's needed to test the retry/skip logic deterministically
    rather than at the mercy of shuffle luck. Does NOT affect
    _build_choices()'s separate random.sample() calls for distractors,
    which still exercise real randomness.
    """
    monkeypatch.setattr(quiz.random, "shuffle", lambda seq: None)


def _real_photo(url="https://upload.wikimedia.org/real.jpg", attribution="Real Photographer / Commons"):
    async def fake(scientific_name, common_name):
        return {"photo_url": url, "attribution": attribution}
    return fake


def _placeholder_photo():
    async def fake(scientific_name, common_name):
        return {"photo_url": "https://placehold.co/x", "attribution": None}
    return fake


def _real_audio(url="https://upload.wikimedia.org/real.ogg", attribution="Real Recordist / Commons"):
    async def fake(bird):
        return {"audio_url": url, "attribution": attribution}
    return fake


def test_get_question_photo_mode_returns_real_media_and_four_choices(monkeypatch):
    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", _real_photo())

    question = asyncio.run(quiz.get_question("photo"))

    assert question["mode"] == "photo"
    assert question["photo_url"] == "https://upload.wikimedia.org/real.jpg"
    assert question["audio_url"] is None
    assert len(question["choices"]) == 4
    scientific_names = {c["scientific_name"] for c in question["choices"]}
    assert question["correct_scientific_name"] in scientific_names
    assert len(scientific_names) == 4


def test_get_question_audio_mode_returns_real_media(monkeypatch):
    monkeypatch.setattr(quiz.bird_audio, "get_audio", _real_audio())

    question = asyncio.run(quiz.get_question("audio"))

    assert question["mode"] == "audio"
    assert question["audio_url"] == "https://upload.wikimedia.org/real.ogg"
    assert question["photo_url"] is None


def test_get_question_includes_the_correct_species_family(monkeypatch):
    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", _real_photo())

    question = asyncio.run(quiz.get_question("photo"))

    assert question["correct_family"] == "Crows, Jays, and Magpies"  # Blue Jay, first in fixed order


def test_get_question_skips_a_flagged_photo_and_retries(monkeypatch):
    # Real, reported bug: a Seaside Sparrow question showed a range map —
    # Commons had *something* (so `attribution` wasn't None, the old skip
    # condition), it just wasn't a photo of the bird. `flagged` is how
    # bird_photos/commons report that; a photo quiz must reject it, not just
    # "no media at all" — see _real_media()'s own docstring.
    calls = []

    async def fake(scientific_name, common_name):
        calls.append(scientific_name)
        if scientific_name == "Corvus brachyrhynchos":  # 3rd in CHECKLIST's fixed order
            return {"photo_url": "https://upload.wikimedia.org/real.jpg", "attribution": "Real / Commons", "flagged": False}
        return {"photo_url": "https://upload.wikimedia.org/a-map.jpg", "attribution": "Someone / Commons", "flagged": True}

    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", fake)

    question = asyncio.run(quiz.get_question("photo"))

    assert question["correct_scientific_name"] == "Corvus brachyrhynchos"
    assert calls[:2] == ["Cyanocitta cristata", "Cyanocitta stelleri"]


def test_get_question_skips_a_placeholder_photo_and_retries(monkeypatch):
    calls = []

    async def fake(scientific_name, common_name):
        calls.append(scientific_name)
        if scientific_name == "Corvus brachyrhynchos":  # 3rd in CHECKLIST's fixed order
            return {"photo_url": "https://upload.wikimedia.org/real.jpg", "attribution": "Real / Commons"}
        return {"photo_url": "https://placehold.co/x", "attribution": None}

    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", fake)

    question = asyncio.run(quiz.get_question("photo"))

    assert question["correct_scientific_name"] == "Corvus brachyrhynchos"
    assert calls[:2] == ["Cyanocitta cristata", "Cyanocitta stelleri"]


def test_family_filter_narrows_the_pool(monkeypatch):
    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", _real_photo())

    question = asyncio.run(quiz.get_question("photo", family="New World Warblers"))

    assert question["correct_scientific_name"] in {"Setophaga petechia", "Cardellina pusilla"}


def test_choices_prefer_the_same_family_when_enough_members_exist(monkeypatch):
    # Blue Jay is first in CHECKLIST's fixed order (no_shuffle), so it's
    # always the question — and its family (corvids) has 3 other members,
    # enough to never need the whole-pool fallback.
    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", _real_photo())

    question = asyncio.run(quiz.get_question("photo"))

    corvid_names = {"Cyanocitta cristata", "Cyanocitta stelleri", "Corvus brachyrhynchos", "Corvus corax"}
    assert {c["scientific_name"] for c in question["choices"]} <= corvid_names


def test_choices_fall_back_to_the_whole_pool_when_family_is_too_small(monkeypatch):
    # No family filter here, deliberately — when one *is* active (see
    # test_choices_prefer_the_same_family_when_enough_members_exist's
    # sibling case above), the pool itself is already restricted to that
    # family, so there's nothing outside it to fall back to; that's correct
    # behavior, not a bug. This test instead exercises an unfiltered pool
    # where the *correct* species' own family (warblers, only 2 total)
    # happens to be smaller than the 3 distractors needed.
    async def fake(scientific_name, common_name):
        if scientific_name == "Setophaga petechia":  # Yellow Warbler, 5th in CHECKLIST's fixed order
            return {"photo_url": "https://upload.wikimedia.org/real.jpg", "attribution": "Real / Commons"}
        return {"photo_url": "https://placehold.co/x", "attribution": None}  # skip every corvid first

    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", fake)

    question = asyncio.run(quiz.get_question("photo"))

    assert question["correct_scientific_name"] == "Setophaga petechia"
    scientific_names = {c["scientific_name"] for c in question["choices"]}
    assert not scientific_names <= {"Setophaga petechia", "Cardellina pusilla"}


def test_get_filter_options_returns_family_counts():
    options = asyncio.run(quiz.get_filter_options())

    assert options == [
        {"name": "Crows, Jays, and Magpies", "count": 4},
        {"name": "New World Warblers", "count": 2},
    ]


def test_no_question_available_when_filter_matches_nothing():
    with pytest.raises(quiz.NoQuestionAvailable):
        asyncio.run(quiz.get_question("photo", family="Nonexistent Family"))


def test_no_question_available_when_all_media_missing(monkeypatch):
    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", _placeholder_photo())

    with pytest.raises(quiz.NoQuestionAvailable):
        asyncio.run(quiz.get_question("photo"))


def test_quiz_question_endpoint(client, monkeypatch):
    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", _real_photo())

    resp = client.get("/quiz/question", params={"mode": "photo"})

    assert resp.status_code == 200
    assert len(resp.json()["choices"]) == 4


def test_quiz_question_endpoint_with_family_filter(client, monkeypatch):
    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", _real_photo())

    resp = client.get("/quiz/question", params={"mode": "photo", "family": "New World Warblers"})

    assert resp.status_code == 200
    assert resp.json()["correct_scientific_name"] in {"Setophaga petechia", "Cardellina pusilla"}


def test_quiz_question_endpoint_rejects_an_invalid_mode(client):
    resp = client.get("/quiz/question", params={"mode": "video"})
    assert resp.status_code == 422


def test_quiz_question_endpoint_503_when_nothing_available(client, monkeypatch):
    monkeypatch.setattr(quiz.bird_photos, "get_stock_photo", _placeholder_photo())

    resp = client.get("/quiz/question", params={"mode": "photo"})

    assert resp.status_code == 503


def test_quiz_question_endpoint_503_without_an_ebird_key(client, monkeypatch):
    async def no_key(region_code):
        raise EBirdConfigError("EBIRD_API_KEY is not set")

    monkeypatch.setattr(quiz.region_repo, "get_checklist", no_key)

    resp = client.get("/quiz/question", params={"mode": "photo"})

    assert resp.status_code == 503


def test_get_another_photo_delegates_to_bird_photos(monkeypatch):
    async def fake_get_different(scientific_name, common_name, exclude_photo_url):
        assert scientific_name == "Ammodramus maritimus"
        assert common_name == "Seaside Sparrow"
        assert exclude_photo_url == "https://upload.wikimedia.org/the-map.jpg"
        return {"photo_url": "https://upload.wikimedia.org/a-real-photo.jpg", "attribution": "Jane Birder / Commons", "flagged": False, "changed": True}

    monkeypatch.setattr(quiz.bird_photos, "get_different_stock_photo", fake_get_different)

    result = asyncio.run(
        quiz.get_another_photo("Ammodramus maritimus", "Seaside Sparrow", "https://upload.wikimedia.org/the-map.jpg")
    )
    assert result["changed"] is True
    assert result["photo_url"] == "https://upload.wikimedia.org/a-real-photo.jpg"


def test_quiz_another_photo_endpoint(client, monkeypatch):
    async def fake_get_different(scientific_name, common_name, exclude_photo_url):
        return {"photo_url": "https://upload.wikimedia.org/different.jpg", "attribution": "Someone / Commons", "flagged": False, "changed": True}

    monkeypatch.setattr(quiz.bird_photos, "get_different_stock_photo", fake_get_different)

    resp = client.get(
        "/quiz/another-photo",
        params={
            "scientific_name": "Ammodramus maritimus",
            "common_name": "Seaside Sparrow",
            "exclude_photo_url": "https://upload.wikimedia.org/the-map.jpg",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["photo_url"] == "https://upload.wikimedia.org/different.jpg"
    assert resp.json()["changed"] is True


def test_quiz_filters_endpoint(client):
    resp = client.get("/quiz/filters")

    assert resp.status_code == 200
    assert resp.json() == [
        {"name": "Crows, Jays, and Magpies", "count": 4},
        {"name": "New World Warblers", "count": 2},
    ]
