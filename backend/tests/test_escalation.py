from datetime import timedelta

from app.config import get_settings
from app.models import Notification, Ticket, TicketEvent
from app.services.events import broker
from app.services.tickets import run_deadline_checks
from tests.conftest import auth


def new_critical(client, db) -> Ticket:
    res = client.post("/tickets", data={"location_code": "BLK-A-F1-R103", "description": "Smoke from the AC unit"})
    ticket = db.query(Ticket).filter(Ticket.ref == res.json()["ref"]).one()
    assert ticket.priority == "critical"
    return ticket


def test_critical_deadline_is_4_hours(client, db, frozen_clock):
    ticket = new_critical(client, db)
    assert ticket.deadline_at - ticket.created_at == timedelta(hours=4)


def test_reminder_then_escalation(client, db, frozen_clock):
    ticket = new_critical(client, db)
    start = frozen_clock.now

    frozen_clock.now = start + timedelta(hours=2)
    assert run_deadline_checks(db) == {"escalated": [], "reminded": []}

    frozen_clock.now = start + timedelta(hours=3, minutes=1)  # past 75% of 4 h
    assert run_deadline_checks(db)["reminded"] == [ticket.ref]
    assert run_deadline_checks(db)["reminded"] == []  # only once

    frozen_clock.now = start + timedelta(hours=4, minutes=1)
    result = run_deadline_checks(db)
    assert result["escalated"] == [ticket.ref]
    db.refresh(ticket)
    assert ticket.escalated_at is not None
    assert db.query(Notification).filter_by(to_addr="estate@educrew.local", channel="email").count() == 1
    assert db.query(TicketEvent).filter_by(ticket_id=ticket.id, action="escalated").count() == 1
    assert any(m["type"] == "ticket.escalated" and m["data"]["ref"] == ticket.ref for m in broker.recent)
    # Escalates once, not every minute.
    frozen_clock.now = start + timedelta(hours=5)
    assert run_deadline_checks(db)["escalated"] == []


def test_resolved_tickets_never_escalate(client, db, frozen_clock):
    ticket = new_critical(client, db)
    client.patch(f"/tickets/{ticket.ref}", json={"status": "resolved"}, headers=auth(client, "electrical"))
    frozen_clock.now += timedelta(hours=10)
    assert ticket.ref not in run_deadline_checks(db)["escalated"]


def test_lowering_priority_moves_deadline_and_clears_escalation(client, db, frozen_clock):
    ticket = new_critical(client, db)
    frozen_clock.now += timedelta(hours=5)
    run_deadline_checks(db)
    db.refresh(ticket)
    assert ticket.escalated_at is not None
    res = client.patch(f"/tickets/{ticket.ref}", json={"priority": "normal"}, headers=auth(client, "electrical"))
    assert res.status_code == 200
    db.refresh(ticket)
    assert ticket.escalated_at is None
    assert ticket.deadline_at == ticket.created_at + timedelta(hours=72)


def test_demo_mode_uses_minutes(client, db, monkeypatch, frozen_clock):
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    ticket = new_critical(client, db)
    assert ticket.deadline_at - ticket.created_at == timedelta(minutes=2)
    frozen_clock.now += timedelta(minutes=3)
    assert run_deadline_checks(db)["escalated"] == [ticket.ref]


def test_demo_shorten_deadline_only_in_demo_mode(client, db, monkeypatch):
    ticket = new_critical(client, db)
    estate = auth(client, "estate")
    assert client.post(f"/tickets/{ticket.ref}/demo-deadline", headers=estate).status_code == 403
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    assert client.post(f"/tickets/{ticket.ref}/demo-deadline", headers=estate).status_code == 200
