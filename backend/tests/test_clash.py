"""The rule that must never break: no suggestion double-books a faculty member (spec C3, C5 acceptance)."""
from datetime import timedelta

import pytest

from app.models import Adjustment, Duty, Faculty, Leave, User
from app.services import adjustments as service
from app.services import clock
from app.services.candidates import find_candidates
from app.services.timetable import DayView, apply_adjustment


def week_dates():
    """Today and the next 6 days: every working weekday once (Sunday has no classes)."""
    return [clock.today() + timedelta(days=i) for i in range(7)]


def clashes_after(view: DayView, adj: Adjustment, cand) -> set:
    items = apply_adjustment(view.items, adj, cand)
    probe = DayView.__new__(DayView)
    probe.date, probe.items, probe.duties, probe.leaves = view.date, items, view.duties, view.leaves
    return probe.clashes()


def all_requests(db):
    """Create one adjustment request for every class unit of every faculty member this week."""
    requests = []
    for d in week_dates():
        view = DayView(db, d)
        for fac in db.query(Faculty).all():
            for periods, _ in view.units_of(fac.id):
                created = service.create_adjustments(db, fac, fac.user, d, periods, "test")
                requests.extend(created)
    return requests


def test_no_suggestion_ever_creates_a_clash(db):
    requests = all_requests(db)
    assert len(requests) >= 80  # the whole seeded week is covered
    kinds = set()
    checked = 0
    for adj in requests:
        view = DayView(db, adj.date, exclude_adjustment_id=adj.id)
        baseline = view.clashes()
        for cand in adj.candidates:
            kinds.add(cand.kind)
            assert view.is_free(cand.candidate_id, adj.periods), "suggested someone who is busy"
            if cand.kind == "swap":
                assert view.is_free(adj.requester_id, cand.swap_periods), "swap clashes for the requester"
            assert clashes_after(view, adj, cand) <= baseline, f"{cand.kind} {cand.candidate_id} creates a clash"
            checked += 1
    assert checked > 500
    assert kinds == {"swap", "substitute"}  # both paths were exercised


def test_sequential_acceptances_never_double_book(db):
    d = clock.today()
    baseline = DayView(db, d).clashes()
    accepted = 0
    for fac in db.query(Faculty).all():
        for periods, _ in DayView(db, d).units_of(fac.id):
            try:
                adj = service.create_adjustments(db, fac, fac.user, d, periods, "away")[0]
            except service.AdjustmentError:
                continue  # this class was already handed over earlier in the loop
            for cand in list(adj.candidates):
                if cand.state != "suggested":
                    continue
                try:
                    service.choose(db, adj, cand.id, fac.user)
                except service.AdjustmentError:
                    continue  # no longer free: correctly refused
                result = service.respond(db, cand, "accept")
                if result["outcome"] == "accepted":
                    accepted += 1
                break
            assert DayView(db, d).clashes() <= baseline
    assert accepted >= 10


def test_lab_request_takes_the_whole_block(db):
    for d in week_dates():
        view = DayView(db, d)
        for fac in db.query(Faculty).all():
            for periods, first in view.units_of(fac.id):
                if first.type == "lab" and len(periods) == 2:
                    adj = service.create_adjustments(db, fac, fac.user, d, [periods[1]], "lab")[0]
                    assert adj.periods == periods
                    for cand in adj.candidates:
                        assert DayView(db, d).is_free(cand.candidate_id, periods)
                        if cand.kind == "swap":
                            assert len(cand.swap_periods) == 2
                    return
    pytest.fail("seed has no lab block this week")


def _first_request(db):
    fac = db.query(Faculty).first()
    for d in week_dates():
        units = DayView(db, d).units_of(fac.id)
        if units:
            return fac, d, units[0][0]
    raise AssertionError("faculty 1 has no classes")


def test_leave_and_duty_exclude_a_candidate(db):
    fac, d, periods = _first_request(db)
    _, first = DayView(db, d).unit_at(fac.id, periods[0])
    adj = Adjustment(requester_id=fac.id, date=d, periods=periods, section=first.section, subject=first.subject,
                     slot_type=first.type, status="open")
    db.add(adj)
    db.flush()
    subs = [s for s in find_candidates(db, adj) if s.kind == "substitute"]
    on_leave, on_duty = subs[0].faculty, subs[1].faculty
    db.add(Leave(faculty_id=on_leave.id, date=d, period=None, reason="sick"))
    db.add(Duty(faculty_id=on_duty.id, date=d, period=periods[-1], kind="Invigilation"))
    db.flush()
    ids = {s.faculty.id for s in find_candidates(db, adj)}
    assert on_leave.id not in ids
    assert on_duty.id not in ids


def test_accept_rechecks_for_clashes(db):
    """If the candidate became busy after the request was sent, accepting must not double-book."""
    fac, d, periods = _first_request(db)
    adj = service.create_adjustments(db, fac, fac.user, d, periods, "away")[0]
    cand = next(c for c in adj.candidates if c.kind == "substitute")
    service.choose(db, adj, cand.id, fac.user)
    db.add(Duty(faculty_id=cand.candidate_id, date=d, period=periods[0], kind="Exam squad"))
    db.commit()
    result = service.respond(db, cand, "accept")
    assert result["outcome"] == "no_longer_free"
    assert cand.state == "unavailable"
    assert DayView(db, d).is_free(cand.candidate_id, periods) is False  # duty still there, no class added
    assert not any(a.adjustment_id == adj.id and a.faculty_id == cand.candidate_id for a in DayView(db, d).items)


def test_hod_override_cannot_double_book(db):
    fac, d, periods = _first_request(db)
    adj = service.create_adjustments(db, fac, fac.user, d, periods, "away")[0]
    view = DayView(db, d)
    busy = next(f for f in db.query(Faculty).all() if f.id != fac.id and not view.is_free(f.id, periods))
    hod = db.query(User).filter(User.role == "hod").one()
    with pytest.raises(service.AdjustmentError):
        service.override(db, adj, busy.id, hod)
