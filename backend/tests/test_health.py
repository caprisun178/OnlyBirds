def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["docs"] == "/docs"


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "ebird_key_configured" in body


def test_health_reports_unconfigured_for_an_empty_string_key(client, monkeypatch):
    # Regression: an env var present but set to "" (e.g. a blank value saved
    # in a host's dashboard) used to read as "configured" here (`is not
    # None`) while `dao/ebird.py#_client()` still rejected it as unset
    # (truthiness) — every real eBird call 503'd despite /health saying
    # everything was fine.
    from app.config import get_settings

    monkeypatch.setenv("EBIRD_API_KEY", "")
    get_settings.cache_clear()
    try:
        resp = client.get("/health")
        assert resp.json()["ebird_key_configured"] is False
    finally:
        get_settings.cache_clear()  # don't leak the empty key into later tests
