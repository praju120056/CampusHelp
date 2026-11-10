from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import get_db
from app.models import Location, Ticket, User
from app.models.tickets import OPEN_STATUSES
from app.routers.deps import TICKET_STAFF
from app.schemas.requests import TicketPatch
from app.schemas.serializers import location_dict, ticket_full, ticket_public, ticket_summary
from app.services import campus_map
from app.services import tickets as ticket_service
from app.services.auth import require_role
from app.services.ratelimit import public_read_limit, ticket_submit_limit

router = APIRouter(tags=["tickets"])


def _location(db: Session, code: str) -> Location:
    loc = db.query(Location).filter(Location.code == code).first()
    if loc is None:
        raise HTTPException(status_code=404, detail="Unknown location. Please scan the QR code again.")
    return loc


def _ticket(db: Session, ref: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.ref == ref.upper()).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


# ---------------------------------------------------------------- public (no login, rate limited)


@router.get("/locations/{code}", dependencies=[Depends(public_read_limit)])
def get_location(code: str, db: Session = Depends(get_db)):
    return location_dict(_location(db, code), with_assets=True)


@router.get("/locations/{code}/qr.png", dependencies=[Depends(public_read_limit)])
def location_qr(code: str, db: Session = Depends(get_db)):
    loc = _location(db, code)
    return Response(content=campus_map.qr_png(loc.code), media_type="image/png")


@router.post("/tickets", dependencies=[Depends(ticket_submit_limit)])
async def submit_ticket(
    location_code: str = Form(...),
    description: str = Form(...),
    category: Optional[str] = Form(None),
    reporter_name: Optional[str] = Form(None),
    reporter_phone: Optional[str] = Form(None),
    reporter_email: Optional[str] = Form(None),
    website: Optional[str] = Form(None),  # honeypot: hidden field humans never fill
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    if website:
        # Bots fill every field. Pretend success, store nothing.
        return {"ref": None, "duplicate": False, "status_url": None, "message": "Thank you, your report was received."}
    loc = _location(db, location_code)
    data = None
    if photo is not None and photo.filename:
        limit = get_settings().max_upload_mb * 1024 * 1024
        data = await photo.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail=f"Photo must be under {get_settings().max_upload_mb} MB")
    result = await run_in_threadpool(  # triage may wait on Gemini; keep the event loop free
        ticket_service.create_ticket,
        db,
        loc,
        description,
        category,
        data,
        reporter_name,
        reporter_phone,
        reporter_email,
    )
    t = result.ticket
    message = (
        "Already reported. We added your report to the existing ticket."
        if result.duplicate
        else "Thank you. Your report has been sent to the maintenance team."
    )
    return {
        "ref": t.ref,
        "duplicate": result.duplicate,
        "report_count": t.report_count,
        "category": t.category,
        "priority": t.priority,
        "summary": t.summary,
        "status_url": f"/t/{t.ref}",
        "message": message,
    }


@router.get("/tickets/{ref}", dependencies=[Depends(public_read_limit)])
def ticket_status(ref: str, db: Session = Depends(get_db)):
    ticket = _ticket(db, ref)
    if ticket.duplicate_of is not None:
        original = db.get(Ticket, ticket.duplicate_of)
        return ticket_public(original) | {"merged_from": ticket.ref}
    return ticket_public(ticket)


# ---------------------------------------------------------------- staff


@router.get("/tickets")
def list_tickets(
    scope: str = "all",
    status: Optional[str] = None,
    category: Optional[str] = None,
    open_only: bool = False,
    limit: int = 200,
    user: User = Depends(require_role(*TICKET_STAFF)),
    db: Session = Depends(get_db),
):
    query = db.query(Ticket).filter(Ticket.duplicate_of.is_(None))
    if scope == "mine" and user.role == "incharge":
        query = query.filter(Ticket.assigned_to == user.id)
    if scope == "escalated":
        query = query.filter(Ticket.escalated_at.isnot(None), Ticket.status.in_(OPEN_STATUSES))
    if status:
        query = query.filter(Ticket.status == status)
    if category:
        query = query.filter(Ticket.category == category)
    if open_only:
        query = query.filter(Ticket.status.in_(OPEN_STATUSES))
    tickets = query.order_by(Ticket.created_at.desc()).limit(min(limit, 500)).all()
    return [ticket_summary(t) for t in tickets]


@router.get("/tickets/{ref}/full")
def ticket_detail(ref: str, user: User = Depends(require_role(*TICKET_STAFF)), db: Session = Depends(get_db)):
    ticket = _ticket(db, ref)
    if ticket.duplicate_of is not None:
        ticket = db.get(Ticket, ticket.duplicate_of)
    return ticket_full(ticket, ticket_service.can_edit(user, ticket)) | {"demo_mode": get_settings().demo_mode}


@router.patch("/tickets/{ref}")
def update_ticket(
    ref: str,
    body: TicketPatch,
    user: User = Depends(require_role("incharge", "estate")),
    db: Session = Depends(get_db),
):
    ticket = ticket_service.update_ticket(db, _ticket(db, ref), user, **body.model_dump())
    return ticket_full(ticket, ticket_service.can_edit(user, ticket))


@router.post("/tickets/{ref}/demo-deadline")
def demo_deadline(ref: str, user: User = Depends(require_role(*TICKET_STAFF)), db: Session = Depends(get_db)):
    ticket = ticket_service.shorten_deadline(db, _ticket(db, ref), user)
    return ticket_full(ticket, ticket_service.can_edit(user, ticket))
