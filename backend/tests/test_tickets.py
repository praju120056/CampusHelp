import json

import httpx
import pytest

from app.config import get_settings
from app.models import Notification, Ticket, User
from app.services import triage
from tests.conftest import auth


def submit(client, code="BLK-A-F2-WRM", text="Tap leaking in the washroom, water on the floor", **extra):
    data = {"location_code": code, "description": text, **extra}
    return client.post("/tickets", data=data)


def test_new_ticket_is_triaged_and_routed(client, db):
    res = submit(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["duplicate"] is False
    assert body["category"] == "plumbing"
    assert body["priority"] == "high"
    ticket = db.query(Ticket).filter(Ticket.ref == body["ref"]).one()
    assert ticket.assignee.email == "plumbing@educrew.local"
    assert ticket.status == "new"
    assert ticket.ai_source == "rules"  # Gemini is off in tests
    # In-app + outbox email to the in-charge, and a live event for the map.
    assert db.query(Notification).filter_by(user_id=ticket.assigned_to, channel="in_app").count() == 1
    assert db.query(Notification).filter_by(to_addr="plumbing@educrew.local", channel="email", status="outbox").count() == 1
    from app.services.events import broker

    assert any(m["type"] == "ticket.created" and m["data"]["ref"] == body["ref"] for m in broker.recent)


def test_status_page_is_public_and_hides_contact_details(client):
    ref = submit(client, reporter_phone="9999999999", reporter_name="Asha").json()["ref"]
    res = client.get(f"/tickets/{ref}")
    assert res.status_code == 200
    assert "9999999999" not in res.text
    assert res.json()["status"] == "new"


def test_second_report_same_location_and_category_is_a_plus_one(client, db):
    first = submit(client).json()
    second = submit(client, text="Water leaking from the pipe under the basin").json()
    assert second["duplicate"] is True
    assert second["ref"] == first["ref"]
    assert second["report_count"] == 2
    original = db.query(Ticket).filter(Ticket.ref == first["ref"]).one()
    db.refresh(original)
    assert original.report_count == 2
    # Only one open ticket at that location.
    open_here = db.query(Ticket).filter(Ticket.location_id == original.location_id, Ticket.duplicate_of.is_(None)).count()
    assert open_here == 1


def test_near_identical_description_is_a_duplicate_even_with_other_category(client):
    first = submit(client, code="BLK-A-F2-R206", text="The projector screen is torn on the left side").json()
    second = submit(client, code="BLK-A-F2-R206", text="the projector screen is torn on the left side!", category="civil").json()
    assert second["duplicate"] is True and second["ref"] == first["ref"]


def test_honeypot_creates_nothing(client, db):
    before = db.query(Ticket).count()
    res = submit(client, website="http://spam.example")
    assert res.status_code == 200
    assert res.json()["ref"] is None
    assert db.query(Ticket).count() == before


def test_public_submission_is_rate_limited(client):
    codes = ["BLK-A-F1-R103", "BLK-A-F2-R203"]
    statuses = [submit(client, code=codes[i % 2], text=f"Bench number {i} is broken").status_code for i in range(11)]
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429


def test_photo_over_5mb_is_rejected(client):
    big = b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 10)
    res = client.post(
        "/tickets",
        data={"location_code": "BLK-A-F1-R103", "description": "Broken chair"},
        files={"photo": ("big.jpg", big, "image/jpeg")},
    )
    assert res.status_code == 413


def test_ticket_is_created_when_gemini_is_down(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "fake-key")

    def boom(*args, **kwargs):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(triage.httpx, "post", boom)
    res = submit(client, code="BLK-A-F1-R103", text="Fan making a loud noise and sparking")
    assert res.status_code == 200
    ticket = db.query(Ticket).filter(Ticket.ref == res.json()["ref"]).one()
    assert ticket.ai_source == "rules"
    assert ticket.category == "electrical"
    assert ticket.priority == "critical"


def test_gemini_answer_is_used_when_available(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "fake-key")
    answer = {"category": "plumbing", "priority": "high", "summary": "Leaking tap in seminar hall", "confidence": 0.91}

    def fake_post(url, json=None, headers=None, timeout=None):
        assert headers["x-goog-api-key"] == "fake-key"
        assert "gemini" in url
        payload = {"candidates": [{"content": {"parts": [{"text": _dumps(answer)}]}}]}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(triage.httpx, "post", fake_post)
    res = submit(client, code="BLK-A-F1-R103", text="tap is leaking")
    ticket = db.query(Ticket).filter(Ticket.ref == res.json()["ref"]).one()
    assert ticket.ai_source == "gemini"
    assert ticket.summary == "Leaking tap in seminar hall"
    assert ticket.ai_confidence == 0.91


def _dumps(obj):
    return json.dumps(obj)


def test_bad_gemini_answer_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "fake-key")

    def fake_post(url, **kwargs):
        payload = {"candidates": [{"content": {"parts": [{"text": '{"category": "aliens", "priority": "high"}'}]}}]}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(triage.httpx, "post", fake_post)
    result = triage.triage("Washroom is dirty and smells", "Washroom", "washroom")
    assert result.source == "rules"
    assert result.category == "housekeeping"


@pytest.mark.parametrize(
    "text,kind,category,priority",
    [
        ("Wi-Fi not working in the lab", "lab", "it", "high"),
        ("Door hinge is loose", "classroom", "civil", "normal"),
        ("Smoke coming from the switch board", "classroom", "electrical", "critical"),
        ("Bins overflowing, please clean", "washroom", "housekeeping", "high"),
        ("Toilet flush is blocked", "washroom", "plumbing", "high"),
    ],
)
def test_rule_based_classifier(text, kind, category, priority):
    result = triage.classify_rules(text, kind)
    assert (result.category, result.priority) == (category, priority)


def test_in_charge_override_reroutes_and_keeps_ai_suggestion(client, db):
    ref = submit(client, code="BLK-A-F1-R103", text="Projector cable is loose").json()["ref"]
    ticket = db.query(Ticket).filter(Ticket.ref == ref).one()
    owner = ticket.assignee.email.split("@")[0]
    res = client.patch(f"/tickets/{ref}", json={"category": "electrical", "priority": "critical"}, headers=auth(client, owner))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["category"] == "electrical"
    assert body["assigned_to"] == "Electrical In-charge"
    assert body["ai"]["category"] == ticket.ai_category
    assert body["ai"]["overridden"] is True


def test_other_in_charge_cannot_edit(client):
    ref = submit(client).json()["ref"]  # plumbing
    res = client.patch(f"/tickets/{ref}", json={"status": "in_progress"}, headers=auth(client, "electrical"))
    assert res.status_code == 403


def test_state_machine(client, db):
    ref = submit(client).json()["ref"]
    plumbing = auth(client, "plumbing")
    assert client.patch(f"/tickets/{ref}", json={"status": "rejected"}, headers=plumbing).status_code == 400
    res = client.patch(f"/tickets/{ref}", json={"worker": "Ravi"}, headers=plumbing)
    assert res.json()["status"] == "assigned"
    assert client.patch(f"/tickets/{ref}", json={"status": "in_progress"}, headers=plumbing).status_code == 200
    assert client.patch(f"/tickets/{ref}", json={"status": "resolved"}, headers=plumbing).status_code == 200
    res = client.patch(f"/tickets/{ref}", json={"status": "in_progress"}, headers=plumbing)
    assert res.status_code == 400


def test_resolving_emails_every_reporter(client, db):
    ref = submit(client, reporter_email="a@example.com").json()["ref"]
    submit(client, text="Basin pipe leaking badly", reporter_email="b@example.com")
    client.patch(f"/tickets/{ref}", json={"status": "resolved"}, headers=auth(client, "plumbing"))
    sent_to = {n.to_addr for n in db.query(Notification).filter(Notification.subject.like("Resolved:%"))}
    assert sent_to == {"a@example.com", "b@example.com"}


def test_map_shows_new_ticket_as_pulsing(client):
    submit(client)
    hod = auth(client, "hod")
    floor = client.get("/map/A/2", headers=hod).json()
    room = next(r for row in floor["rows"] for r in row["rooms"] if r["code"] == "BLK-A-F2-WRM")
    assert room["is_new"] is True
    assert room["level"] == "amber"
    assert room["label"] == "1 open"
    summary = client.get("/map/summary", headers=hod).json()
    assert summary["overdue"] == 2  # seeded


def test_qr_contains_only_the_location_code():
    from app.services.campus_map import qr_url

    url = qr_url("BLK-A-F1-R101")
    assert url.endswith("/r/BLK-A-F1-R101")
    assert "Classroom" not in url
