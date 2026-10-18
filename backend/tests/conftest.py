import re
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.dao.bug_report_repo import InMemoryBugReportRepo
from app.dao.notification_repo import InMemoryNotificationRepo
from app.dao.observation_repo import InMemoryObservationRepo
from app.dao.pin_repo import InMemoryPinRepo
from app.dao.species_repo import InMemorySpeciesRepo
from app.dao.sticker_repo import InMemoryStickerRepo
from app.dao.user_repo import InMemoryUserRepo
from app.config import get_settings
from app.main import app
from app.services.auth import create_session_token

TEST_SESSION_SECRET = "test-session-secret"
TEST_GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
_USER_IN_PATH = re.compile(r"/users/(?!by-id/)([^/?]+)")


def _acting_user(url, kwargs) -> str:
    """Who a test request is acting as: the `{user_id}` in a
    `/users/{user_id}/...` path, else a `user_id` / `auth_provider_id` in
    the JSON body or query, else 'u1' (e.g. PATCH /observations/{id})."""
    match = _USER_IN_PATH.search(str(url))
    if match:
        return unquote(match.group(1))
    body = kwargs.get("json")
    if isinstance(body, dict):
        for key in ("user_id", "auth_provider_id"):
            if body.get(key):
                return body[key]
    params = kwargs.get("params")
    if isinstance(params, dict) and params.get("user_id"):
        return params["user_id"]
    query = parse_qs(urlsplit(str(url)).query)
    if query.get("user_id"):
        return query["user_id"][0]
    return "u1"


class SignedInClient(TestClient):
    """A TestClient that signs every request in as the user it's acting for
    (see `_acting_user`), with a real session token — so the suite written
    before auth existed still exercises the real auth checks instead of
    bypassing them. Pass your own `Authorization` header to override, or use
    `anon_client` for signed-out requests. Auth-specific behavior (401/403,
    sign-in) is tested in test_auth.py."""

    def request(self, method, url, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        if not any(k.lower() == "authorization" for k in headers):
            token, _ = create_session_token(_acting_user(url, kwargs))
            headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)




@pytest.fixture(autouse=True)
def no_live_media_lookups(monkeypatch):
    """Keep the suite offline (see docs/ebird-api.md's "no test hits the live
    API" rule) and each test's candidate photos/audio deterministic.
    Individual tests can still monkeypatch `commons.search_photo` /
    `commons.search_audio` themselves to exercise the lookup path — see
    test_bird_photos.py and test_bird_audio.py."""
    async def _no_media(*args, **kwargs):
        return None

    monkeypatch.setattr("app.dao.commons.search_photo", _no_media)
    monkeypatch.setattr("app.dao.commons.search_audio", _no_media)
    monkeypatch.setattr("app.dao.bird_photos._cache", {})
    monkeypatch.setattr("app.dao.bird_audio._cache", {})

    async def _no_summary(title):
        return None

    async def _no_sections(title):
        return {}

    monkeypatch.setattr("app.dao.wikipedia.get_summary", _no_summary)
    monkeypatch.setattr("app.dao.wikipedia.get_sections", _no_sections)

    async def _no_taxon(scientific_name):
        return None

    monkeypatch.setattr("app.dao.inaturalist.find_species_taxon", _no_taxon)
    monkeypatch.setattr("app.services.species._extinct_cache", {})
    # Isolate species_repo too — any test not using the `client` fixture
    # below (which resets this to its own fresh InMemorySpeciesRepo) would
    # otherwise hit the real Postgres-backed repo, since DATABASE_URL is set
    # in this repo's own .env. Both targets, same reason `client` patches
    # both: `app/services/species.py` does `from app.dao.species_repo import
    # species_repo` (a direct name import), so patching only the origin
    # module's attribute wouldn't affect the name already bound in services.py.
    fresh_species_repo = InMemorySpeciesRepo()
    monkeypatch.setattr("app.dao.species_repo.species_repo", fresh_species_repo)
    monkeypatch.setattr("app.services.species.species_repo", fresh_species_repo)
    # bird_photos' cache now writes through to a real file on disk (see its
    # module docstring) — tests exercise cache-miss paths constantly, which
    # would otherwise spam the real species_photo_cache.json with test
    # fixture junk (or fail outright in a read-only CI checkout).
    monkeypatch.setattr("app.dao.bird_photos._save_cache_file", lambda: None)
    # Never load the real photo-ID model in tests (app/main.py's startup
    # warm-up) — it's slow and needs ~1GB of RAM. Env var too, for tests
    # that rebuild Settings via cache_clear().
    monkeypatch.setenv("PHOTO_ID_PRELOAD", "false")
    monkeypatch.setattr(get_settings(), "photo_id_preload", False)
    # Isolate earned stickers too, or awards from one test leak into the
    # next (confirmed: a fresh user showed sticker_count 1).
    fresh_stickers = InMemoryStickerRepo()
    monkeypatch.setattr("app.dao.sticker_repo.sticker_repo", fresh_stickers)
    monkeypatch.setattr("app.services.stickers.sticker_repo", fresh_stickers)


@pytest.fixture()
def client(monkeypatch):
    # `log_observation()` calls `ebird.region_for_point()` — which calls
    # `get_hotspots_near()` — for every observation logged with lat/lng,
    # which is most of the ones posted through this `client`. A real
    # `EBIRD_API_KEY` happens to be set in this repo's `.env` (pydantic
    # settings loads it by default), so without this default, a plain
    # `POST /observations` test would silently make a real, slow eBird call
    # — the same offline-tests rule `no_live_media_lookups` above exists
    # for. Scoped to this fixture (not a separate blanket autouse one)
    # deliberately: test_ebird.py tests `get_hotspots_near()` itself
    # directly and never uses `client`, so it's never affected; tests that
    # *do* use `client` and want real `get_hotspots_near()` behavior
    # (test_trip.py's `_stub_sources()`, etc.) already monkeypatch it
    # themselves, which simply overrides this default.
    async def _no_hotspots(lat, lng, dist_km=25):
        return []

    monkeypatch.setattr("app.dao.ebird.get_hotspots_near", _no_hotspots)

    # Sign-in configured with test values (never whatever's in .env). Env
    # vars too, not just the cached Settings — some tests `cache_clear()` it
    # (test_health.py) and the rebuilt one must still have them.
    monkeypatch.setenv("SESSION_SECRET", TEST_SESSION_SECRET)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", TEST_GOOGLE_CLIENT_ID)
    monkeypatch.setattr(get_settings(), "session_secret", TEST_SESSION_SECRET)
    monkeypatch.setattr(get_settings(), "google_client_id", TEST_GOOGLE_CLIENT_ID)

    # Isolate each test from the process-wide in-memory stores.
    fresh = InMemoryObservationRepo()
    monkeypatch.setattr("app.dao.observation_repo.observation_repo", fresh)
    monkeypatch.setattr("app.services.observation.observation_repo", fresh)
    monkeypatch.setattr("app.services.sightings.observation_repo", fresh)
    fresh_users = InMemoryUserRepo()
    monkeypatch.setattr("app.dao.user_repo.user_repo", fresh_users)
    monkeypatch.setattr("app.services.user.user_repo", fresh_users)
    fresh_pins = InMemoryPinRepo()
    monkeypatch.setattr("app.dao.pin_repo.pin_repo", fresh_pins)
    monkeypatch.setattr("app.services.pins.pin_repo", fresh_pins)
    fresh_notifications = InMemoryNotificationRepo()
    monkeypatch.setattr("app.dao.notification_repo.notification_repo", fresh_notifications)
    monkeypatch.setattr("app.services.pins.notification_repo", fresh_notifications)
    monkeypatch.setattr("app.services.notifications.notification_repo", fresh_notifications)
    monkeypatch.setattr("app.services.stickers.notification_repo", fresh_notifications)
    fresh_bug_reports = InMemoryBugReportRepo()
    monkeypatch.setattr("app.dao.bug_report_repo.bug_report_repo", fresh_bug_reports)
    monkeypatch.setattr("app.services.feedback.bug_report_repo", fresh_bug_reports)
    fresh_species = InMemorySpeciesRepo()
    monkeypatch.setattr("app.dao.species_repo.species_repo", fresh_species)
    monkeypatch.setattr("app.services.species.species_repo", fresh_species)
    with SignedInClient(app) as c:
        yield c


TEST_ADMIN_EMAIL = "admin@example.com"


@pytest.fixture()
def admin_client(client, monkeypatch):
    """Same isolated app as `client`, signed in as a user whose email is in
    ADMIN_EMAILS — for the /admin/... routes."""
    monkeypatch.setattr(get_settings(), "admin_emails", TEST_ADMIN_EMAIL)
    client.post("/users", json={"auth_provider_id": "admin", "email": TEST_ADMIN_EMAIL})
    token, _ = create_session_token("admin")
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        yield c


@pytest.fixture()
def anon_client(client):
    """Same isolated app as `client`, but requests carry no session — i.e.
    a signed-out user. Tokens can be added per request via `headers=`."""
    with TestClient(app) as c:
        yield c