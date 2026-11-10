"""Ticket lifecycle (B4–B9, B11, B12): create with triage, duplicate +1, routing, state changes."""
import difflib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CategoryAssignee, Location, Ticket, TicketEvent, User
from app.models.tickets import CATEGORIES, OPEN_STATUSES, PRIORITIES
from app.services import clock
from app.services.events import broker
from app.services.notify import notify_role, notify_user, queue_email
from app.services.settings_store import get_setting
from app.services.triage import triage

REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I, easy to read aloud
PUBLIC_ACTOR = "Reporter (QR)"
DUPLICATE_SIMILARITY = 0.85

TRANSITIONS = {
    "new": {"assigned", "in_progress", "resolved", "rejected"},
    "assigned": {"in_progress", "resolved", "rejected"},
    "in_progress": {"assigned", "resolved", "rejected"},
    "resolved": set(),
    "rejected": set(),
}
STATUS_LABELS = {
    "new": "New",
    "assigned": "Assigned",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "rejected": "Rejected",
}
PHOTO_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}


class TicketError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class CreateResult:
    ticket: Ticket
    duplicate: bool


def new_ref(db: Session) -> str:
    while True:
        ref = "".join(secrets.choice(REF_ALPHABET) for _ in range(6))
        if not db.query(Ticket.id).filter(Ticket.ref == ref).first():
            return ref


def deadline_delta(db: Session, priority: str) -> timedelta:
    if get_settings().demo_mode:
        return timedelta(minutes=get_setting(db, "demo_deadline_minutes")[priority])
    return timedelta(hours=get_setting(db, "deadline_hours")[priority])


def location_label(loc: Location) -> str:
    return f"{loc.room_name} ({loc.code}), Block {loc.block}, Floor {loc.floor}"


def route(db: Session, category: str) -> Optional[User]:
    row = db.get(CategoryAssignee, category)
    return row.user if row else None


def save_photo(data: bytes) -> Optional[tuple[str, str]]:
    """Validate and store a photo. Returns (url, mime) or None if it isn't a usable image."""
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise TicketError(f"Photo must be under {settings.max_upload_mb} MB", 413)
    try:
        img = Image.open(BytesIO(data))
        fmt = img.format
        img.verify()
    except Exception:  # noqa: BLE001
        return None
    if fmt not in PHOTO_FORMATS:
        return None
    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{PHOTO_FORMATS[fmt]}"
    (folder / name).write_bytes(data)
    return f"/uploads/{name}", Image.MIME.get(fmt, "image/jpeg")


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def find_duplicate(db: Session, location_id: int, category: str, description: str) -> Optional[Ticket]:
    """B11: an open ticket at the same location with the same category, or a near-identical description."""
    open_tickets = (
        db.query(Ticket)
        .filter(
            Ticket.location_id == location_id,
            Ticket.status.in_(OPEN_STATUSES),
            Ticket.duplicate_of.is_(None),
        )
        .order_by(Ticket.created_at)
        .all()
    )
    for ticket in open_tickets:
        if ticket.category == category:
            return ticket
    wanted = _normalise(description)
    for ticket in open_tickets:
        if difflib.SequenceMatcher(None, _normalise(ticket.description), wanted).ratio() >= DUPLICATE_SIMILARITY:
            return ticket
    return None


def create_ticket(
    db: Session,
    location: Location,
    description: str,
    category_choice: Optional[str] = None,
    photo: Optional[bytes] = None,
    reporter_name: Optional[str] = None,
    reporter_phone: Optional[str] = None,
    reporter_email: Optional[str] = None,
) -> CreateResult:
    description = (description or "").strip()
    if len(description) < 5:
        raise TicketError("Please describe the problem in a few words")
    if category_choice and category_choice not in CATEGORIES:
        category_choice = None

    photo_url = photo_mime = None
    if photo:
        saved = save_photo(photo)
        if saved:
            photo_url, photo_mime = saved

    result = triage(
        description,
        location_label(location),
        location.kind,
        photo if photo_mime else None,
        photo_mime,
    )
    category = category_choice or result.category
    priority = result.priority
    now = clock.now()
    reporter = {
        "reporter_name": (reporter_name or "").strip()[:120] or None,
        "reporter_phone": (reporter_phone or "").strip()[:30] or None,
        "reporter_email": (reporter_email or "").strip()[:200] or None,
    }
    ai_fields = {
        "summary": result.summary,
        "ai_category": result.category,
        "ai_priority": result.priority,
        "ai_confidence": result.confidence,
        "ai_source": result.source,
    }

    original = find_duplicate(db, location.id, category, description)
    if original is not None:
        original.report_count += 1
        db.add(
            Ticket(
                ref=new_ref(db),
                location_id=location.id,
                category=category,
                priority=priority,
                status=original.status,
                description=description,
                photo_url=photo_url,
                assigned_to=original.assigned_to,
                deadline_at=original.deadline_at,
                duplicate_of=original.id,
                created_at=now,
                **reporter,
                **ai_fields,
            )
        )
        db.add(
            TicketEvent(
                ticket_id=original.id,
                actor=reporter["reporter_name"] or PUBLIC_ACTOR,
                action="plus_one",
                note=f"Reported again (+1, now {original.report_count}): {description[:300]}",
            )
        )
        db.commit()
        broker.publish("tickets", "ticket.updated", {"ref": original.ref, "location": location.code, "reason": "plus_one"})
        return CreateResult(original, True)

    assignee = route(db, category)
    ticket = Ticket(
        ref=new_ref(db),
        location_id=location.id,
        category=category,
        priority=priority,
        status="new",
        description=description,
        photo_url=photo_url,
        assigned_to=assignee.id if assignee else None,
        deadline_at=now + deadline_delta(db, priority),
        created_at=now,
        **reporter,
        **ai_fields,
    )
    db.add(ticket)
    db.flush()
    source = "Gemini" if result.source == "gemini" else "keyword rules (AI offline)"
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            actor=reporter["reporter_name"] or PUBLIC_ACTOR,
            action="created",
            note=f"Triage by {source}: {result.category} / {result.priority}, confidence {result.confidence:.0%}",
        )
    )
    if assignee:
        db.add(TicketEvent(ticket_id=ticket.id, actor="System", action="routed", note=f"Routed to {assignee.name}"))
        notify_user(
            db,
            assignee,
            f"New {priority} ticket {ticket.ref}: {ticket.summary}",
            f"{location_label(location)}\n\n{description}\n\nDue by {ticket.deadline_at:%d %b %H:%M}.",
            link=f"/tickets/{ticket.ref}",
        )
    db.commit()
    broker.publish(
        "tickets",
        "ticket.created",
        {"ref": ticket.ref, "location": location.code, "priority": priority, "category": category},
    )
    return CreateResult(ticket, False)


def can_edit(user: User, ticket: Ticket) -> bool:
    if user.role == "estate":
        return True
    return user.role == "incharge" and ticket.assigned_to == user.id


def update_ticket(
    db: Session,
    ticket: Ticket,
    user: User,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    assigned_to: Optional[int] = None,
    worker: Optional[str] = None,
    note: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> Ticket:
    if ticket.duplicate_of is not None:
        raise TicketError("This report was merged into another ticket", 409)
    if not can_edit(user, ticket):
        raise TicketError("Only the assigned in-charge or the Estate Officer can change this ticket", 403)
    now = clock.now()
    events: list[tuple[str, str]] = []

    if category and category != ticket.category:
        if category not in CATEGORIES:
            raise TicketError("Unknown category")
        old = ticket.category
        ticket.category = category
        hint = f" (AI suggested {ticket.ai_category})" if ticket.ai_category else ""
        events.append(("category_changed", f"Category {old} → {category}{hint}"))
        new_owner = route(db, category)
        if new_owner and new_owner.id != ticket.assigned_to:
            ticket.assigned_to = new_owner.id
            events.append(("routed", f"Re-routed to {new_owner.name}"))
            notify_user(db, new_owner, f"Ticket {ticket.ref} moved to you", ticket.summary, link=f"/tickets/{ticket.ref}")

    if priority and priority != ticket.priority:
        if priority not in PRIORITIES:
            raise TicketError("Unknown priority")
        old = ticket.priority
        ticket.priority = priority
        ticket.deadline_at = ticket.created_at + deadline_delta(db, priority)
        if ticket.deadline_at > now:
            ticket.escalated_at = None
            ticket.reminded_at = None
        hint = f" (AI suggested {ticket.ai_priority})" if ticket.ai_priority else ""
        events.append(("priority_changed", f"Priority {old} → {priority}{hint}; due {ticket.deadline_at:%d %b %H:%M}"))

    if assigned_to and assigned_to != ticket.assigned_to:
        owner = db.get(User, assigned_to)
        if owner is None or owner.role not in ("incharge", "estate"):
            raise TicketError("Tickets can only be assigned to an in-charge or the Estate Officer")
        ticket.assigned_to = owner.id
        events.append(("reassigned", f"Assigned to {owner.name}"))
        notify_user(db, owner, f"Ticket {ticket.ref} assigned to you", ticket.summary, link=f"/tickets/{ticket.ref}")

    if worker is not None and (worker.strip() or None) != ticket.worker:
        ticket.worker = worker.strip()[:120] or None
        events.append(("worker", f"Work given to {ticket.worker}" if ticket.worker else "Worker cleared"))
        if status is None and ticket.status == "new":
            status = "assigned"

    if status and status != ticket.status:
        if status not in TRANSITIONS.get(ticket.status, set()):
            raise TicketError(f"Cannot move a ticket from {STATUS_LABELS[ticket.status]} to {STATUS_LABELS.get(status, status)}")
        if status == "rejected":
            if not (rejection_reason or "").strip():
                raise TicketError("Give a reason for rejecting")
            ticket.rejection_reason = rejection_reason.strip()[:300]
        old = ticket.status
        ticket.status = status
        detail = f": {ticket.rejection_reason}" if status == "rejected" else ""
        events.append(("status_changed", f"{STATUS_LABELS[old]} → {STATUS_LABELS[status]}{detail}"))
        if status == "resolved":
            ticket.resolved_at = now
            _notify_reporters_resolved(db, ticket)

    if note and note.strip():
        events.append(("note", note.strip()[:1000]))

    if not events:
        return ticket
    for action, text in events:
        db.add(TicketEvent(ticket_id=ticket.id, actor=user.name, action=action, note=text))
    ticket.updated_at = now
    db.commit()
    broker.publish("tickets", "ticket.updated", {"ref": ticket.ref, "location": ticket.location.code})
    return ticket


def _notify_reporters_resolved(db: Session, ticket: Ticket) -> None:
    emails = {ticket.reporter_email} if ticket.reporter_email else set()
    for child in db.query(Ticket).filter(Ticket.duplicate_of == ticket.id).all():
        if child.reporter_email:
            emails.add(child.reporter_email)
    for email in emails:
        queue_email(
            db,
            email,
            f"Resolved: your report {ticket.ref} ({ticket.location.room_name})",
            f"Thank you for reporting \"{ticket.summary}\". It has been fixed.",
            link=f"/t/{ticket.ref}",
        )


def shorten_deadline(db: Session, ticket: Ticket, user: User, seconds: int = 20) -> Ticket:
    """Demo mode only: bring the deadline close so escalation can be shown live."""
    if not get_settings().demo_mode:
        raise TicketError("Only available when DEMO_MODE is on", 403)
    if user.role not in ("incharge", "estate", "hod"):
        raise TicketError("Not allowed", 403)
    if not ticket.is_open:
        raise TicketError("Ticket is already closed")
    ticket.deadline_at = clock.now() + timedelta(seconds=seconds)
    ticket.escalated_at = None
    db.add(TicketEvent(ticket_id=ticket.id, actor=user.name, action="demo", note=f"Deadline shortened to {seconds}s (demo)"))
    db.commit()
    broker.publish("tickets", "ticket.updated", {"ref": ticket.ref, "location": ticket.location.code})
    return ticket


# ---------------------------------------------------------------- deadlines (B7)


def run_deadline_checks(db: Session) -> dict:
    """Send pre-deadline reminders and escalate overdue tickets to the Estate Officer."""
    now = clock.now()
    fraction = float(get_setting(db, "reminder")["fraction"])
    candidates = (
        db.query(Ticket)
        .filter(
            Ticket.status.in_(OPEN_STATUSES),
            Ticket.duplicate_of.is_(None),
            Ticket.escalated_at.is_(None),
        )
        .all()
    )
    escalated, reminded = [], []
    for ticket in candidates:
        room = ticket.location.room_name
        if ticket.deadline_at <= now:
            ticket.escalated_at = now
            db.add(
                TicketEvent(
                    ticket_id=ticket.id,
                    actor="System",
                    action="escalated",
                    note=f"Deadline {ticket.deadline_at:%d %b %H:%M} passed; escalated to the Estate Officer",
                )
            )
            notify_role(
                db,
                "estate",
                f"ESCALATED {ticket.ref}: {ticket.summary} ({room})",
                f"Priority {ticket.priority}, due {ticket.deadline_at:%d %b %H:%M}, still {STATUS_LABELS[ticket.status]}.",
                link=f"/tickets/{ticket.ref}",
            )
            if ticket.assignee and ticket.assignee.role != "estate":
                notify_user(
                    db,
                    ticket.assignee,
                    f"Overdue and escalated: {ticket.ref}",
                    ticket.summary,
                    link=f"/tickets/{ticket.ref}",
                    email=False,
                )
            escalated.append(ticket)
        elif ticket.reminded_at is None and now >= ticket.created_at + (ticket.deadline_at - ticket.created_at) * fraction:
            ticket.reminded_at = now
            db.add(
                TicketEvent(
                    ticket_id=ticket.id,
                    actor="System",
                    action="reminder",
                    note=f"Reminder sent: due {ticket.deadline_at:%d %b %H:%M}",
                )
            )
            if ticket.assignee:
                notify_user(
                    db,
                    ticket.assignee,
                    f"Reminder: {ticket.ref} due {ticket.deadline_at:%H:%M}",
                    f"{ticket.summary} ({room})",
                    link=f"/tickets/{ticket.ref}",
                )
            reminded.append(ticket)
    if escalated or reminded:
        db.commit()
        for ticket in escalated:
            broker.publish("tickets", "ticket.escalated", {"ref": ticket.ref, "location": ticket.location.code})
        for ticket in reminded:
            broker.publish("tickets", "ticket.updated", {"ref": ticket.ref, "location": ticket.location.code})
    return {"escalated": [t.ref for t in escalated], "reminded": [t.ref for t in reminded]}
