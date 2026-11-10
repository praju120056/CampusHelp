"""Live Ticket Map (B14–B18). With no drawn floor plan, rooms are laid out as a grid:
one row per corridor side, ordered by sort_order (room number)."""
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional

import qrcode
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Location, Ticket
from app.models.tickets import OPEN_STATUSES
from app.services import clock

SIDE_ORDER = {"N": 0, "S": 1, "E": 2, "W": 3}


def room_status(tickets: list[Ticket], now: datetime) -> dict:
    """Worst open ticket decides the colour: red = critical or overdue, amber = any open, green = none."""
    overdue = any(t.deadline_at <= now for t in tickets)
    critical = any(t.priority == "critical" for t in tickets)
    if overdue:
        level, label = "red", "Overdue"
    elif critical:
        level, label = "red", "Critical"
    elif tickets:
        level, label = "amber", f"{len(tickets)} open"
    else:
        level, label = "green", "OK"
    return {
        "level": level,
        "label": label,
        "open_count": len(tickets),
        "overdue": overdue,
        "critical": critical,
        "is_new": any(t.status == "new" for t in tickets),
        "escalated": any(t.escalated_at is not None for t in tickets),
    }


def _open_tickets(db: Session, location_ids: list[int], category: Optional[str], status: Optional[str]):
    query = db.query(Ticket).filter(
        Ticket.location_id.in_(location_ids),
        Ticket.status.in_(OPEN_STATUSES),
        Ticket.duplicate_of.is_(None),
    )
    if category:
        query = query.filter(Ticket.category == category)
    if status:
        query = query.filter(Ticket.status == status)
    return query.all()


def floors(db: Session) -> list[dict]:
    rows = db.query(Location.block, Location.floor).distinct().order_by(Location.block, Location.floor).all()
    return [{"block": b, "floor": f} for b, f in rows]


def floor_map(db: Session, block: str, floor: int, category: Optional[str] = None, status: Optional[str] = None) -> dict:
    locations = db.query(Location).filter(Location.block == block, Location.floor == floor).all()
    locations.sort(key=lambda loc: (SIDE_ORDER.get(loc.side, 9), loc.sort_order))
    now = clock.now()
    by_location: dict[int, list[Ticket]] = defaultdict(list)
    for ticket in _open_tickets(db, [loc.id for loc in locations], category, status):
        by_location[ticket.location_id].append(ticket)

    rows: dict[str, list] = defaultdict(list)
    for loc in locations:
        rows[loc.side].append(
            {
                "code": loc.code,
                "room_name": loc.room_name,
                "kind": loc.kind,
                "map_shape_id": loc.map_shape_id,
                **room_status(by_location[loc.id], now),
            }
        )
    return {
        "block": block,
        "floor": floor,
        "rows": [{"side": side, "rooms": rooms} for side, rooms in sorted(rows.items(), key=lambda kv: SIDE_ORDER.get(kv[0], 9))],
    }


def summary(db: Session) -> dict:
    now = clock.now()
    open_tickets = (
        db.query(Ticket).filter(Ticket.status.in_(OPEN_STATUSES), Ticket.duplicate_of.is_(None)).all()
    )
    since = now - timedelta(days=30)
    resolved = (
        db.query(Ticket)
        .filter(Ticket.status == "resolved", Ticket.duplicate_of.is_(None), Ticket.resolved_at >= since)
        .all()
    )
    hours = [(t.resolved_at - t.created_at).total_seconds() / 3600 for t in resolved if t.resolved_at]
    start_of_day = now.replace(hour=0, minute=0, second=0)
    return {
        "open": len(open_tickets),
        "overdue": sum(1 for t in open_tickets if t.deadline_at <= now),
        "escalated": sum(1 for t in open_tickets if t.escalated_at is not None),
        "new": sum(1 for t in open_tickets if t.status == "new"),
        "avg_resolution_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "resolved_today": sum(1 for t in resolved if t.resolved_at and t.resolved_at >= start_of_day),
    }


def location_history(db: Session, location: Location, limit: int = 20) -> dict:
    tickets = (
        db.query(Ticket)
        .filter(Ticket.location_id == location.id, Ticket.duplicate_of.is_(None))
        .order_by(Ticket.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "open": [t for t in tickets if t.is_open],
        "closed": [t for t in tickets if not t.is_open],
    }


def qr_url(code: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/r/{code}"


def qr_png(code: str) -> bytes:
    """B1: the QR holds only the location code in the URL; details come from the database."""
    img = qrcode.make(qr_url(code), box_size=10, border=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
