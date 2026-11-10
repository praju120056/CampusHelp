"""Turn ORM objects into JSON-ready dicts. Formatting only: no business rules here."""
from typing import Optional

from app.models import Adjustment, AdjustmentCandidate, Location, Notification, Ticket, User
from app.services import clock
from app.services.tickets import STATUS_LABELS
from app.services.timetable import periods_label

PUBLIC_EVENT_ACTIONS = {"created", "routed", "status_changed", "plus_one", "escalated", "worker"}


def iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "faculty_id": user.faculty.id if user.faculty else None,
    }


def location_dict(loc: Location, with_assets: bool = False) -> dict:
    data = {
        "code": loc.code,
        "block": loc.block,
        "floor": loc.floor,
        "room_name": loc.room_name,
        "kind": loc.kind,
    }
    if with_assets:
        data["assets"] = [a.name for a in loc.assets]
    return data


def _ticket_flags(t: Ticket) -> dict:
    now = clock.now()
    return {
        "overdue": t.is_open and t.deadline_at <= now,
        "escalated": t.escalated_at is not None,
    }


def ticket_public(t: Ticket) -> dict:
    """Status page view (no login): no reporter contact details, no internal notes."""
    return {
        "ref": t.ref,
        "status": t.status,
        "status_label": STATUS_LABELS[t.status],
        "category": t.category,
        "priority": t.priority,
        "summary": t.summary,
        "location": location_dict(t.location),
        "report_count": t.report_count,
        "rejection_reason": t.rejection_reason,
        "created_at": iso(t.created_at),
        "updated_at": iso(t.updated_at),
        "resolved_at": iso(t.resolved_at),
        "events": [
            {"action": e.action, "at": iso(e.created_at), "note": e.note if e.action in ("status_changed", "worker") else None}
            for e in t.events
            if e.action in PUBLIC_EVENT_ACTIONS
        ],
    }


def ticket_summary(t: Ticket) -> dict:
    return {
        "ref": t.ref,
        "status": t.status,
        "status_label": STATUS_LABELS[t.status],
        "category": t.category,
        "priority": t.priority,
        "summary": t.summary,
        "location": location_dict(t.location),
        "assigned_to": t.assignee.name if t.assignee else None,
        "assigned_to_id": t.assigned_to,
        "worker": t.worker,
        "report_count": t.report_count,
        "deadline_at": iso(t.deadline_at),
        "created_at": iso(t.created_at),
        "updated_at": iso(t.updated_at),
        "resolved_at": iso(t.resolved_at),
        **_ticket_flags(t),
    }


def ticket_full(t: Ticket, can_edit: bool) -> dict:
    return ticket_summary(t) | {
        "description": t.description,
        "photo_url": t.photo_url,
        "ai": {
            "category": t.ai_category,
            "priority": t.ai_priority,
            "confidence": t.ai_confidence,
            "source": t.ai_source,
            "overridden": (t.ai_category is not None and t.ai_category != t.category)
            or (t.ai_priority is not None and t.ai_priority != t.priority),
        },
        "reporter": {"name": t.reporter_name, "phone": t.reporter_phone, "email": t.reporter_email},
        "rejection_reason": t.rejection_reason,
        "reminded_at": iso(t.reminded_at),
        "escalated_at": iso(t.escalated_at),
        "events": [
            {"actor": e.actor, "action": e.action, "note": e.note, "at": iso(e.created_at)} for e in t.events
        ],
        "can_edit": can_edit,
    }


def candidate_dict(c: AdjustmentCandidate) -> dict:
    return {
        "id": c.id,
        "faculty_id": c.candidate_id,
        "name": c.candidate.name,
        "designation": c.candidate.designation,
        "kind": c.kind,
        "rank": c.rank,
        "score": c.score,
        "breakdown": c.score_breakdown,
        "swap_periods": c.swap_periods,
        "swap_label": periods_label(c.swap_periods) if c.swap_periods else None,
        "swap_subject": c.swap_subject,
        "state": c.state,
        "requested_at": iso(c.requested_at),
        "responded_at": iso(c.responded_at),
    }


def adjustment_dict(a: Adjustment, with_candidates: bool = True) -> dict:
    chosen = next((c for c in a.candidates if c.id == a.chosen_candidate_id), None)
    data = {
        "id": a.id,
        "requester_id": a.requester_id,
        "requester": a.requester.name,
        "date": a.date.isoformat(),
        "periods": a.periods,
        "periods_label": periods_label(a.periods),
        "section": a.section,
        "subject": a.subject,
        "slot_type": a.slot_type,
        "reason": a.reason,
        "status": a.status,
        "note": a.note,
        "overridden": a.overridden_by is not None,
        "chosen": candidate_dict(chosen) if chosen else None,
        "created_at": iso(a.created_at),
    }
    if with_candidates:
        data["candidates"] = [candidate_dict(c) for c in a.candidates]
    return data


def incoming_request_dict(c: AdjustmentCandidate) -> dict:
    a = c.adjustment
    return {
        "candidate_id": c.id,
        "adjustment_id": a.id,
        "requester": a.requester.name,
        "date": a.date.isoformat(),
        "periods_label": periods_label(a.periods),
        "section": a.section,
        "subject": a.subject,
        "reason": a.reason,
        "kind": c.kind,
        "swap_label": periods_label(c.swap_periods) if c.swap_periods else None,
        "swap_subject": c.swap_subject,
        "state": c.state,
        "requested_at": iso(c.requested_at),
    }


def notification_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "channel": n.channel,
        "to": n.to_addr,
        "subject": n.subject,
        "body": n.body,
        "link": n.link,
        "status": n.status,
        "read": n.read,
        "error": n.error,
        "created_at": iso(n.created_at),
    }
