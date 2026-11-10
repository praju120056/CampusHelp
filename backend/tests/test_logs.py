from app.models import AuditLog, Faculty, LogDay, WorkLog
from app.services import clock
from app.services.events import broker
from app.services.timetable import DayView
from tests.conftest import auth


def test_prefill_comes_from_the_timetable(client, db):
    day = client.get("/logs/prefill", headers=auth(client, "faculty1")).json()
    assert day["submitted"] is False
    fac = db.query(Faculty).first()
    units = DayView(db, clock.today()).units_of(fac.id)
    class_entries = [e for e in day["entries"] if e["type"] in ("theory", "lab")]
    assert len(class_entries) == len(units)
    for entry, (periods, a) in zip(class_entries, units):
        assert entry["period"] == periods[0]
        assert entry["units"] == len(periods)  # a 2-period lab is one entry with 2 units
        assert entry["subject"] == a.subject


def test_submit_in_one_call_logs_audits_and_notifies(client, db):
    headers = auth(client, "faculty1")
    day = client.get("/logs/prefill", headers=headers).json()
    res = client.post("/logs", json={"date": day["date"], "entries": day["entries"]}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["submitted"] is True
    fac = db.query(Faculty).first()
    assert db.query(LogDay).filter_by(faculty_id=fac.id, date=clock.today()).count() == 1
    saved = db.query(WorkLog).filter_by(faculty_id=fac.id, date=clock.today()).count()
    assert saved == len(day["entries"])
    assert db.query(AuditLog).filter_by(entity="work_log", action="create").count() == saved
    assert any(m["type"] == "log.saved" for m in broker.recent)
    status = client.get("/analytics/today", headers=auth(client, "hod")).json()
    assert next(r for r in status["faculty"] if r["name"] == "Faculty 1")["logged"] is True


def test_edits_and_deletes_are_audited(client, db):
    headers = auth(client, "faculty1")
    day = client.get("/logs/prefill", headers=headers).json()
    entries = client.post("/logs", json={"date": day["date"], "entries": day["entries"]}, headers=headers).json()["entries"]
    entries[0]["topic"] = "Gradient descent"
    entries.append({"type": "meeting", "units": 1, "topic": "IQAC meeting"})
    client.post("/logs", json={"date": day["date"], "entries": entries}, headers=headers)
    assert db.query(AuditLog).filter_by(entity="work_log", action="update").count() == 1
    client.post("/logs", json={"date": day["date"], "entries": entries[:1]}, headers=headers)
    assert db.query(AuditLog).filter_by(entity="work_log", action="delete").count() == len(entries) - 1


def test_future_dates_are_refused(client):
    res = client.post("/logs", json={"date": "2030-01-01", "entries": []}, headers=auth(client, "faculty1"))
    assert res.status_code == 400


def test_hod_today_view_and_reminders(client):
    hod = auth(client, "hod")
    status = client.get("/analytics/today", headers=hod).json()
    assert status["logged"] == 6  # seeded: faculty 2, 4, 6, 8, 10, 12
    assert len(status["not_logged"]) == 6
    assert client.post("/analytics/remind", headers=hod).json()["reminded"] == 6
