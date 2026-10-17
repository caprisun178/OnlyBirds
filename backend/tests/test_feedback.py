def test_report_rejects_empty_message(client):
    resp = client.post("/feedback", json={"message": ""})
    assert resp.status_code == 422


def test_report_persists_as_a_bug_report_not_started(client):
    resp = client.post(
        "/feedback",
        json={
            "message": "The map pins are all red.",
            "screen": "home",
            "url": "https://onlybirds.example/app",
            "user_id": "u1",
            "user_agent": "Mozilla/5.0",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["message"] == "The map pins are all red."
    assert body["screen"] == "home"
    assert body["url"] == "https://onlybirds.example/app"
    assert body["user_id"] == "u1"
    assert body["user_agent"] == "Mozilla/5.0"
    assert body["status"] == "not_started"
    assert body["owner"] is None
    assert body["id"]
    assert body["created_at"]


def test_report_with_only_a_message_still_works(client):
    # screen/url/user_id/user_agent are all optional.
    resp = client.post("/feedback", json={"message": "Something's off."})
    assert resp.status_code == 201
    body = resp.json()
    assert body["screen"] is None
    assert body["status"] == "not_started"


def test_admin_can_list_bug_reports_newest_first(admin_client):
    admin_client.post("/feedback", json={"message": "first report"})
    admin_client.post("/feedback", json={"message": "second report"})

    resp = admin_client.get("/admin/bug-reports")
    assert resp.status_code == 200
    messages = [r["message"] for r in resp.json()]
    assert messages == ["second report", "first report"]


def test_admin_can_update_bug_report_status(admin_client):
    created = admin_client.post("/feedback", json={"message": "a real bug"}).json()

    resp = admin_client.patch(f"/admin/bug-reports/{created['id']}", json={"status": "fixed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "fixed"
    assert body["id"] == created["id"]

    # Persisted, not just echoed back.
    listed = admin_client.get("/admin/bug-reports").json()
    assert next(r for r in listed if r["id"] == created["id"])["status"] == "fixed"


def test_admin_can_set_status_to_investigating(admin_client):
    created = admin_client.post("/feedback", json={"message": "a real bug"}).json()
    resp = admin_client.patch(f"/admin/bug-reports/{created['id']}", json={"status": "investigating"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "investigating"


def test_admin_can_take_ownership_without_touching_status(admin_client):
    created = admin_client.post("/feedback", json={"message": "a real bug"}).json()

    resp = admin_client.patch(f"/admin/bug-reports/{created['id']}", json={"owner": "sparisi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "sparisi"
    assert body["status"] == "not_started"  # untouched — only owner was sent


def test_admin_can_set_status_and_owner_together(admin_client):
    created = admin_client.post("/feedback", json={"message": "a real bug"}).json()
    resp = admin_client.patch(
        f"/admin/bug-reports/{created['id']}", json={"status": "investigating", "owner": "sparisi"}
    )
    body = resp.json()
    assert body["status"] == "investigating"
    assert body["owner"] == "sparisi"


def test_admin_update_rejects_unknown_status(admin_client):
    created = admin_client.post("/feedback", json={"message": "a real bug"}).json()
    resp = admin_client.patch(f"/admin/bug-reports/{created['id']}", json={"status": "wontfix"})
    assert resp.status_code == 422


def test_admin_update_on_unknown_report_is_404(admin_client):
    resp = admin_client.patch("/admin/bug-reports/does-not-exist", json={"status": "fixed"})
    assert resp.status_code == 404


def test_admin_routes_need_sign_in(anon_client):
    assert anon_client.get("/admin/bug-reports").status_code == 401
    assert anon_client.patch("/admin/bug-reports/x", json={"status": "fixed"}).status_code == 401


def test_admin_routes_reject_non_admins(client, admin_client):
    # `client` is signed in as an ordinary user (u1), not in ADMIN_EMAILS.
    created = client.post("/feedback", json={"message": "a real bug"}).json()
    assert client.get("/admin/bug-reports").status_code == 403
    assert client.patch(f"/admin/bug-reports/{created['id']}", json={"status": "fixed"}).status_code == 403


def test_nobody_is_admin_when_admin_emails_is_empty(admin_client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_emails", "")
    assert admin_client.get("/admin/bug-reports").status_code == 403


def test_admin_email_match_is_case_insensitive(admin_client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_emails", "  Admin@Example.COM , someone@else.org")
    assert admin_client.get("/admin/bug-reports").status_code == 200


def test_signed_in_report_is_attributed_from_the_session(anon_client, admin_client):
    from app.services.auth import create_session_token

    token, _ = create_session_token("u1")
    anon_client.post(
        "/feedback",
        json={"message": "spoofed?", "user_id": "u2"},  # body claims u2...
        headers={"Authorization": f"Bearer {token}"},  # ...but the session is u1
    )
    reports = admin_client.get("/admin/bug-reports").json()
    assert reports[0]["user_id"] == "u1"


def test_signed_out_report_has_no_user(anon_client, admin_client):
    anon_client.post("/feedback", json={"message": "anonymous", "user_id": "u2"})
    reports = admin_client.get("/admin/bug-reports").json()
    assert reports[0]["user_id"] is None
