import re
import time

from app.models import Adjustment, AdjustmentCandidate, Notification, WorkLog
from app.services import clock
from tests.conftest import auth


def request_first_class(client, headers):
    day = client.get("/timetable/me", headers=headers).json()
    unit = day["units"][0]
    started = time.perf_counter()
    res = client.post("/adjustments", json={"date": day["date"], "periods": unit["periods"], "reason": "FDP"},
                      headers=headers)
    elapsed = time.perf_counter() - started
    assert res.status_code == 200, res.text
    return res.json()[0], elapsed


def token_from_outbox(db, email: str) -> str:
    note = (
        db.query(Notification)
        .filter(Notification.to_addr == email, Notification.channel == "email", Notification.body.like("%/respond/%"))
        .order_by(Notification.id.desc())
        .first()
    )
    return re.search(r"/respond/([\w-]+)\?action=accept", note.body).group(1)


def test_suggestions_are_ranked_explained_and_fast(client):
    adj, elapsed = request_first_class(client, auth(client, "faculty1"))
    assert elapsed < 2.0
    cands = adj["candidates"]
    assert cands, "expected suggestions"
    tiers = [c["breakdown"]["tier"] for c in cands]
    assert tiers == sorted(tiers)  # swaps, then qualified substitutes, then the rest
    for c in cands:
        b = c["breakdown"]
        assert b["free"] is True
        assert {"weekly_load", "recent_substitutions", "subject_match"} <= b.keys()
    for tier in set(tiers):
        loads = [c["breakdown"]["weekly_load"] for c in cands if c["breakdown"]["tier"] == tier]
        assert loads == sorted(loads)  # lowest load first within each group


def test_decline_moves_to_next_and_accept_updates_everything(client, db):
    faculty1 = auth(client, "faculty1")
    adj, _ = request_first_class(client, faculty1)
    first, second = adj["candidates"][0], adj["candidates"][1]

    res = client.post(f"/adjustments/{adj['id']}/choose", json={"candidate_id": first["id"]}, headers=faculty1)
    assert res.json()["status"] == "pending"

    # Email link: viewing changes nothing; declining moves on to the next candidate.
    first_email = f"{first['name'].lower().replace(' ', '')}@educrew.local"
    token = token_from_outbox(db, first_email)
    view = client.get(f"/adjustments/token/{token}").json()
    assert view["used"] is False and view["state"] == "requested"
    res = client.post("/adjustments/respond-token", json={"token": token, "action": "decline"})
    assert res.status_code == 200, res.text
    assert res.json()["next_candidate"] == second["name"]
    # Single-use: the same link can't be used again.
    assert client.post("/adjustments/respond-token", json={"token": token, "action": "accept"}).status_code == 410

    # The second candidate accepts in the app.
    second_login = auth(client, second["name"].lower().replace(" ", ""))
    incoming = client.get("/adjustments/mine", headers=second_login).json()["incoming"]
    assert incoming[0]["adjustment_id"] == adj["id"]
    res = client.post(f"/adjustments/{adj['id']}/respond", json={"action": "accept"}, headers=second_login)
    assert res.json()["status"] == "accepted"

    logs = db.query(WorkLog).filter(WorkLog.adjustment_id == adj["id"]).all()
    assert len(logs) == 2 and all(log.tag == "adjustment" for log in logs)
    assert db.query(Notification).filter(Notification.subject.like("Class adjusted:%")).count() >= 1  # HOD told

    grid = client.get(f"/timetable/day?date={adj['date']}", headers=faculty1).json()
    cells = [c for s in grid["sections"] for c in s["cells"].values() if c["kind"] != "regular"]
    assert any(c["faculty"] == second["name"] for c in cells)


def test_hod_can_cancel_and_override(client, db):
    faculty1 = auth(client, "faculty1")
    hod = auth(client, "hod")
    adj, _ = request_first_class(client, faculty1)
    free = [f for f in client.get(f"/adjustments/{adj['id']}/free-faculty", headers=hod).json() if f["free"]]
    busy = [f for f in client.get(f"/adjustments/{adj['id']}/free-faculty", headers=hod).json() if not f["free"]]
    assert free and busy

    res = client.post(f"/adjustments/{adj['id']}/override", json={"faculty_id": busy[0]["faculty_id"]}, headers=hod)
    assert res.status_code == 409
    res = client.post(f"/adjustments/{adj['id']}/override", json={"faculty_id": free[0]["faculty_id"]}, headers=hod)
    assert res.status_code == 200
    assert res.json()["status"] == "accepted" and res.json()["overridden"] is True
    assert db.query(WorkLog).filter(WorkLog.adjustment_id == adj["id"]).count() == 2

    res = client.post(f"/adjustments/{adj['id']}/cancel", headers=hod)
    assert res.json()["status"] == "cancelled"
    assert db.query(WorkLog).filter(WorkLog.adjustment_id == adj["id"]).count() == 0


def test_cannot_request_past_dates_or_twice(client):
    faculty1 = auth(client, "faculty1")
    res = client.post("/adjustments", json={"date": "2020-01-01", "periods": [1], "reason": ""}, headers=faculty1)
    assert res.status_code == 400
    adj, _ = request_first_class(client, faculty1)
    res = client.post("/adjustments", json={"date": adj["date"], "periods": adj["periods"], "reason": ""}, headers=faculty1)
    assert res.status_code == 409


def test_everyone_declining_exhausts_and_tells_hod(client, db):
    faculty1 = auth(client, "faculty1")
    adj, _ = request_first_class(client, faculty1)
    client.post(f"/adjustments/{adj['id']}/choose", json={"candidate_id": adj["candidates"][0]["id"]}, headers=faculty1)
    for _ in range(len(adj["candidates"])):
        row = db.query(AdjustmentCandidate).filter_by(adjustment_id=adj["id"], state="requested").first()
        if row is None:
            break
        db.refresh(row)
        login = auth(client, row.candidate.name.lower().replace(" ", ""))
        client.post(f"/adjustments/{adj['id']}/respond", json={"action": "decline"}, headers=login)
    a = db.get(Adjustment, adj["id"])
    db.refresh(a)
    assert a.status == "exhausted"
    assert db.query(Notification).filter(Notification.subject.like("Adjustment needs HOD:%")).count() >= 1


def test_today_is_the_frozen_date():
    assert clock.today().isoformat() == "2026-11-10"
