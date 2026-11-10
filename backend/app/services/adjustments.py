"""Class adjustment lifecycle (C1, C5–C8): request → choose → accept/decline → logs + HOD notice."""
import hashlib
import secrets
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Adjustment, AdjustmentCandidate, Faculty, User, WorkLog
from app.services import audit, clock
from app.services.candidates import store_candidates, subject_matches
from app.services.events import broker
from app.services.notify import absolute_link, notify_role, notify_user
from app.services.settings_store import get_setting
from app.services.timetable import DayView, periods_label

ACTIVE = ("open", "pending", "accepted")


class AdjustmentError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def describe(adj: Adjustment, cand: Optional[AdjustmentCandidate] = None) -> str:
    when = f"{adj.date:%a %d %b}, {periods_label(adj.periods)}"
    base = f"{adj.section} {adj.subject} on {when}"
    if cand is not None and cand.kind == "swap":
        return (
            f"Swap on {adj.date:%a %d %b}: you take {adj.section} {adj.subject} in {periods_label(adj.periods)}; "
            f"{adj.requester.name} takes your {adj.section} {cand.swap_subject} in {periods_label(cand.swap_periods)}"
        )
    return base


def _publish(adj: Adjustment, event: str) -> None:
    broker.publish(
        "adjustments",
        event,
        {"id": adj.id, "status": adj.status, "requester_id": adj.requester_id, "date": adj.date.isoformat()},
    )


def _hods(db: Session) -> list[User]:
    return db.query(User).filter(User.role == "hod").all()


# ---------------------------------------------------------------- create


def create_adjustments(
    db: Session, requester: Faculty, user: User, d: date, periods: list[int], reason: str
) -> list[Adjustment]:
    if d < clock.today():
        raise AdjustmentError("Pick today or a later date")
    if not periods:
        raise AdjustmentError("Pick at least one class")
    view = DayView(db, d)

    # C1: group the chosen periods into class units; a lab block is always taken whole.
    units: list[tuple[list[int], object]] = []
    covered: set[int] = set()
    for period in sorted(set(periods)):
        if period in covered:
            continue
        unit = view.unit_at(requester.id, period)
        if unit is None:
            raise AdjustmentError(f"You have no class in P{period} on {d:%a %d %b}")
        units.append(unit)
        covered.update(unit[0])

    active = (
        db.query(Adjustment)
        .filter(Adjustment.requester_id == requester.id, Adjustment.date == d, Adjustment.status.in_(ACTIVE))
        .all()
    )
    created: list[Adjustment] = []
    for unit_periods, first in units:
        if any(set(a.periods) & set(unit_periods) for a in active):
            raise AdjustmentError(f"You already have a request for {periods_label(unit_periods)}", 409)
        adj = Adjustment(
            requester_id=requester.id,
            date=d,
            periods=list(unit_periods),
            section=first.section,
            subject=first.subject,
            slot_type=first.type,
            reason=(reason or "").strip()[:500],
            status="open",
        )
        db.add(adj)
        db.flush()
        rows = store_candidates(db, adj)
        if not rows:
            adj.status = "exhausted"
            for hod in _hods(db):
                notify_user(
                    db,
                    hod,
                    f"No substitute found: {requester.name}",
                    f"{describe(adj)}. Nobody is free; please assign someone.",
                    link="/hod/adjustments",
                )
        audit.record(db, user.id, "adjustment", adj.id, "create", {"periods": adj.periods, "reason": adj.reason})
        created.append(adj)
    db.commit()
    for adj in created:
        _publish(adj, "adjustment.created")
    return created


# ---------------------------------------------------------------- validity


def still_valid(db: Session, adj: Adjustment, cand: AdjustmentCandidate) -> bool:
    """Re-check against the current timetable (other adjustments may have been accepted since)."""
    view = DayView(db, adj.date, exclude_adjustment_id=adj.id)
    mine = {a.period: a for a in view.assignments_of(adj.requester_id)}
    if any(p not in mine or mine[p].section != adj.section for p in adj.periods):
        return False
    if not view.is_free(cand.candidate_id, adj.periods):
        return False
    if cand.kind == "swap":
        swap = cand.swap_periods or []
        theirs = {a.period: a for a in view.assignments_of(cand.candidate_id)}
        if any(q not in theirs or theirs[q].section != adj.section for q in swap):
            return False
        if not view.is_free(adj.requester_id, swap):
            return False
    return True


# ---------------------------------------------------------------- choose / request


def _request(db: Session, adj: Adjustment, cand: AdjustmentCandidate) -> str:
    token = secrets.token_urlsafe(24)
    cand.token_hash = hash_token(token)
    cand.token_used_at = None
    cand.state = "requested"
    cand.requested_at = clock.now()
    adj.status = "pending"
    adj.chosen_candidate_id = cand.id
    link = f"/respond/{token}"
    body = (
        f"{adj.requester.name} asks you to take a class.\n\n{describe(adj, cand)}\n"
        f"Reason: {adj.reason or '—'}\n\n"
        f"Accept: {absolute_link(link)}?action=accept\nDecline: {absolute_link(link)}?action=decline\n"
        "(Each link works once.)"
    )
    notify_user(db, cand.candidate.user, f"Class adjustment request from {adj.requester.name}", body, link=link)
    return token


def choose(db: Session, adj: Adjustment, candidate_row_id: int, user: User) -> str:
    if user.role != "hod" and (user.faculty is None or user.faculty.id != adj.requester_id):
        raise AdjustmentError("Only the requester or the HOD can choose", 403)
    if adj.status == "pending":
        raise AdjustmentError("Still waiting for the current candidate to reply", 409)
    if adj.status not in ("open", "exhausted"):
        raise AdjustmentError(f"This request is {adj.status}", 409)
    cand = db.get(AdjustmentCandidate, candidate_row_id)
    if cand is None or cand.adjustment_id != adj.id:
        raise AdjustmentError("Unknown candidate", 404)
    if cand.state != "suggested":
        raise AdjustmentError(f"{cand.candidate.name} is already {cand.state}", 409)
    if not still_valid(db, adj, cand):
        cand.state = "unavailable"
        db.commit()
        _publish(adj, "adjustment.updated")
        raise AdjustmentError(f"{cand.candidate.name} is no longer free. Pick another suggestion.", 409)
    token = _request(db, adj, cand)
    audit.record(db, user.id, "adjustment", adj.id, "choose", {"candidate": cand.candidate_id, "kind": cand.kind})
    db.commit()
    _publish(adj, "adjustment.updated")
    return token


def _advance(db: Session, adj: Adjustment) -> Optional[AdjustmentCandidate]:
    """C5: after a decline, ask the next suggestion that is still free."""
    for cand in adj.candidates:
        if cand.state != "suggested":
            continue
        if still_valid(db, adj, cand):
            _request(db, adj, cand)
            return cand
        cand.state = "unavailable"
    adj.status = "exhausted"
    adj.chosen_candidate_id = None
    msg = f"{describe(adj)}: every suggested colleague declined or is busy."
    notify_user(db, adj.requester.user, "No one available for your class", msg, link="/adjust", email=False)
    for hod in _hods(db):
        notify_user(db, hod, f"Adjustment needs HOD: {adj.requester.name}", msg, link="/hod/adjustments")
    return None


# ---------------------------------------------------------------- respond


def _write_logs(db: Session, adj: Adjustment, cand: AdjustmentCandidate) -> None:
    """C6: both sides get a work-log entry tagged 'adjustment'."""
    w = get_setting(db, "workload_weights")
    req, other = adj.requester, cand.candidate
    n = len(adj.periods)
    first = min(adj.periods)
    common = {"date": adj.date, "section": adj.section, "tag": "adjustment", "adjustment_id": adj.id}
    if cand.kind == "swap":
        swap = cand.swap_periods or []
        db.add(WorkLog(faculty_id=other.id, type=adj.slot_type, units=n, weight=n * w.get(adj.slot_type, 0),
                       period=first, subject=adj.subject, topic=f"Swap with {req.name}", **common))
        db.add(WorkLog(faculty_id=req.id, type=cand.swap_type or "theory", units=len(swap),
                       weight=len(swap) * w.get(cand.swap_type or "theory", 0), period=min(swap),
                       subject=cand.swap_subject, topic=f"Swap with {other.name}", **common))
    else:
        db.add(WorkLog(faculty_id=other.id, type="substitution", units=n, weight=n * w["substitution"],
                       period=first, subject=adj.subject, topic=f"Substitution for {req.name}", **common))
        db.add(WorkLog(faculty_id=req.id, type="adjusted", units=n, weight=n * w["adjusted"],
                       period=first, subject=adj.subject, topic=f"Class taken by {other.name}", **common))


def _accepted(db: Session, adj: Adjustment, cand: AdjustmentCandidate, by_hod: Optional[User] = None) -> None:
    cand.state = "accepted"
    adj.status = "accepted"
    adj.chosen_candidate_id = cand.id
    if by_hod is not None:
        adj.overridden_by = by_hod.id
    _write_logs(db, adj, cand)
    what = describe(adj, cand)
    taker = cand.candidate.name
    for hod in _hods(db):
        if by_hod is None or hod.id != by_hod.id:
            notify_user(db, hod, f"Class adjusted: {adj.requester.name} → {taker}", what, link="/hod/adjustments")
    notify_user(db, adj.requester.user, f"{taker} will take your class", what, link="/adjust")
    if by_hod is not None:
        notify_user(db, cand.candidate.user, f"HOD assigned you a class", what, link="/adjust")


def respond(db: Session, cand: AdjustmentCandidate, action: str, user: Optional[User] = None) -> dict:
    if action not in ("accept", "decline"):
        raise AdjustmentError("Action must be accept or decline")
    adj = cand.adjustment
    if cand.state != "requested" or adj.status != "pending" or cand.token_used_at is not None:
        raise AdjustmentError("This request is no longer open", 409)
    now = clock.now()
    cand.responded_at = now
    cand.token_used_at = now  # single use, whichever way it was answered
    actor_id = user.id if user else cand.candidate.user_id
    result: dict = {"adjustment_id": adj.id}

    if action == "accept" and still_valid(db, adj, cand):
        _accepted(db, adj, cand)
        result |= {"outcome": "accepted"}
    else:
        if action == "accept":  # accepted, but a clash appeared since the request was sent
            cand.state = "unavailable"
            result |= {"outcome": "no_longer_free"}
        else:
            cand.state = "declined"
            result |= {"outcome": "declined"}
        nxt = _advance(db, adj)
        result["next_candidate"] = nxt.candidate.name if nxt else None
        if action == "decline":
            note = f"{cand.candidate.name} declined." + (f" Asking {nxt.candidate.name} next." if nxt else "")
            notify_user(db, adj.requester.user, "Substitute declined", f"{describe(adj)}. {note}", link="/adjust", email=False)
    audit.record(db, actor_id, "adjustment", adj.id, f"respond_{action}", {"candidate": cand.candidate_id, **result})
    result["status"] = adj.status
    db.commit()
    _publish(adj, "adjustment.updated")
    if adj.status == "accepted":
        broker.publish("logs", "log.saved", {"date": adj.date.isoformat(), "reason": "adjustment"})
    return result


def candidate_for_token(db: Session, token: str) -> AdjustmentCandidate:
    cand = db.query(AdjustmentCandidate).filter(AdjustmentCandidate.token_hash == hash_token(token)).first()
    if cand is None:
        raise AdjustmentError("This link is not valid", 404)
    return cand


def respond_by_token(db: Session, token: str, action: str) -> dict:
    cand = candidate_for_token(db, token)
    if cand.token_used_at is not None:
        raise AdjustmentError("This link has already been used", 410)
    return respond(db, cand, action)


# ---------------------------------------------------------------- views


def free_faculty(db: Session, adj: Adjustment) -> list[dict]:
    """For the HOD override picker: who is free for this class, and why the others are not."""
    view = DayView(db, adj.date, exclude_adjustment_id=adj.id)
    out = []
    for fac in db.query(Faculty).order_by(Faculty.id).all():
        if fac.id == adj.requester_id:
            continue
        busy = view.busy(fac.id)
        reasons = sorted({busy[p] for p in adj.periods if p in busy})
        out.append({"faculty_id": fac.id, "name": fac.name, "free": not reasons, "busy_reason": "; ".join(reasons),
                    "subject_match": subject_matches(fac, adj.subject)})
    return out


def my_classes(db: Session, faculty: Faculty, d: date) -> dict:
    """The requester's classes on a date (lab blocks as one unit), with any active request on each."""
    view = DayView(db, d)
    active = (
        db.query(Adjustment)
        .filter(Adjustment.requester_id == faculty.id, Adjustment.date == d, Adjustment.status.in_(ACTIVE))
        .all()
    )
    # Classes already handed over are no longer in the faculty's day, so list them from their requests.
    units = []
    for periods, a in view.units_of(faculty.id):
        request = next((x for x in active if set(x.periods) & set(periods)), None)
        units.append({
            "periods": periods, "label": periods_label(periods), "section": a.section, "subject": a.subject,
            "type": a.type, "kind": a.kind, "request_id": request.id if request else None,
            "request_status": request.status if request else None,
        })
    for x in active:
        if x.status == "accepted" and not any(set(u["periods"]) & set(x.periods) for u in units):
            units.append({
                "periods": x.periods, "label": periods_label(x.periods), "section": x.section, "subject": x.subject,
                "type": x.slot_type, "kind": "handed_over", "request_id": x.id, "request_status": x.status,
            })
    units.sort(key=lambda u: u["periods"][0])
    return {"date": d.isoformat(), "day": d.strftime("%A"), "units": units, "busy": view.busy(faculty.id)}


# ---------------------------------------------------------------- cancel / override (C7)


def _undo_accepted(db: Session, adj: Adjustment) -> None:
    db.query(WorkLog).filter(WorkLog.adjustment_id == adj.id).delete(synchronize_session=False)
    for cand in adj.candidates:
        if cand.state in ("accepted", "requested"):
            cand.state = "withdrawn"
            notify_user(db, cand.candidate.user, "Class adjustment cancelled", describe(adj, cand), link="/adjust", email=False)


def cancel(db: Session, adj: Adjustment, user: User) -> Adjustment:
    is_owner = user.faculty is not None and user.faculty.id == adj.requester_id
    if not (is_owner or user.role == "hod"):
        raise AdjustmentError("Only the requester or the HOD can cancel", 403)
    if adj.status == "cancelled":
        return adj
    was_accepted = adj.status == "accepted"
    _undo_accepted(db, adj)
    adj.status = "cancelled"
    adj.chosen_candidate_id = None
    if user.role == "hod" and not is_owner:
        notify_user(db, adj.requester.user, "HOD cancelled your class adjustment", describe(adj), link="/adjust", email=False)
    audit.record(db, user.id, "adjustment", adj.id, "cancel")
    db.commit()
    _publish(adj, "adjustment.updated")
    if was_accepted:
        broker.publish("logs", "log.saved", {"date": adj.date.isoformat(), "reason": "adjustment"})
    return adj


def override(db: Session, adj: Adjustment, faculty_id: int, hod: User, note: str = "") -> Adjustment:
    """HOD assigns a substitute directly. Still clash-checked."""
    if adj.status == "cancelled":
        raise AdjustmentError("This request was cancelled", 409)
    fac = db.get(Faculty, faculty_id)
    if fac is None or fac.id == adj.requester_id:
        raise AdjustmentError("Pick another faculty member")
    view = DayView(db, adj.date, exclude_adjustment_id=adj.id)
    if not view.is_free(fac.id, adj.periods):
        busy = view.busy(fac.id)
        why = "; ".join(sorted({busy[p] for p in adj.periods if p in busy}))
        raise AdjustmentError(f"{fac.name} is not free: {why}", 409)
    was_accepted = adj.status == "accepted"
    _undo_accepted(db, adj)
    cand = next((c for c in adj.candidates if c.candidate_id == fac.id and c.kind == "substitute"), None)
    if cand is None:
        cand = AdjustmentCandidate(
            candidate_id=fac.id,
            kind="substitute",
            rank=len(adj.candidates) + 1,
            score=0,
            score_breakdown={"free": True, "subject_match": subject_matches(fac, adj.subject), "assigned_by_hod": True},
            state="suggested",
        )
        adj.candidates.append(cand)
        db.flush()
    adj.note = (note or "").strip()[:500] or adj.note
    _accepted(db, adj, cand, by_hod=hod)
    audit.record(db, hod.id, "adjustment", adj.id, "override", {"candidate": fac.id, "replaced_accepted": was_accepted})
    db.commit()
    _publish(adj, "adjustment.updated")
    broker.publish("logs", "log.saved", {"date": adj.date.isoformat(), "reason": "adjustment"})
    return adj
