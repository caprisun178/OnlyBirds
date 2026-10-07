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


def test_admin_can_list_bug_reports_newest_first(client):
    client.post("/feedback", json={"message": "first report"})
    client.post("/feedback", json={"message": "second report"})

    resp = client.get("/admin/bug-reports")
    assert resp.status_code == 200
    messages = [r["message"] for r in resp.json()]
    assert messages == ["second report", "first report"]


def test_admin_can_update_bug_report_status(client):
    created = client.post("/feedback", json={"message": "a real bug"}).json()

    resp = client.patch(f"/admin/bug-reports/{created['id']}", json={"status": "fixed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "fixed"
    assert body["id"] == created["id"]

    # Persisted, not just echoed back.
    listed = client.get("/admin/bug-reports").json()
    assert next(r for r in listed if r["id"] == created["id"])["status"] == "fixed"


def test_admin_can_set_status_to_investigating(client):
    created = client.post("/feedback", json={"message": "a real bug"}).json()
    resp = client.patch(f"/admin/bug-reports/{created['id']}", json={"status": "investigating"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "investigating"


def test_admin_can_take_ownership_without_touching_status(client):
    created = client.post("/feedback", json={"message": "a real bug"}).json()

    resp = client.patch(f"/admin/bug-reports/{created['id']}", json={"owner": "sparisi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "sparisi"
    assert body["status"] == "not_started"  # untouched — only owner was sent


def test_admin_can_set_status_and_owner_together(client):
    created = client.post("/feedback", json={"message": "a real bug"}).json()
    resp = client.patch(
        f"/admin/bug-reports/{created['id']}", json={"status": "investigating", "owner": "sparisi"}
    )
    body = resp.json()
    assert body["status"] == "investigating"
    assert body["owner"] == "sparisi"


def test_admin_update_rejects_unknown_status(client):
    created = client.post("/feedback", json={"message": "a real bug"}).json()
    resp = client.patch(f"/admin/bug-reports/{created['id']}", json={"status": "wontfix"})
    assert resp.status_code == 422


def test_admin_update_on_unknown_report_is_404(client):
    resp = client.patch("/admin/bug-reports/does-not-exist", json={"status": "fixed"})
    assert resp.status_code == 404
