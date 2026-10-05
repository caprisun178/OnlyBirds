from app.dao import email as email_dao


def test_report_rejects_empty_message(client):
    resp = client.post("/feedback", json={"message": ""})
    assert resp.status_code == 422


def test_report_returns_503_when_email_not_configured(client):
    # Default test settings have no SMTP_HOST / SMTP_USER / SMTP_PASSWORD /
    # REPORT_EMAIL_TO.
    resp = client.post("/feedback", json={"message": "The map pins are all red."})
    assert resp.status_code == 503


def test_report_sends_email_when_configured(client, monkeypatch):
    sent = {}

    async def fake_send_email(subject, body):
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(email_dao, "is_configured", lambda: True)
    monkeypatch.setattr(email_dao, "send_email", fake_send_email)

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
    assert resp.status_code == 202
    assert resp.json() == {"status": "sent"}
    assert "The map pins are all red." in sent["body"]
    assert "Screen: home" in sent["body"]
    assert "URL: https://onlybirds.example/app" in sent["body"]
    assert "User: u1" in sent["body"]
    assert "Browser: Mozilla/5.0" in sent["body"]
    assert "home" in sent["subject"]
