from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Adjustment, AdjustmentCandidate, Faculty, User
from app.routers.deps import current_faculty
from app.schemas.requests import AdjustmentIn, ChooseIn, OverrideIn, RespondIn, TokenRespondIn
from app.schemas.serializers import adjustment_dict, incoming_request_dict
from app.services import adjustments as service
from app.services.auth import get_current_user, require_role
from app.services.ratelimit import token_respond_limit

router = APIRouter(prefix="/adjustments", tags=["adjustments"])


def _adjustment(db: Session, adjustment_id: int) -> Adjustment:
    adj = db.get(Adjustment, adjustment_id)
    if adj is None:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    return adj


def _can_view(user: User, adj: Adjustment) -> bool:
    if user.role == "hod":
        return True
    if user.faculty is None:
        return False
    return user.faculty.id == adj.requester_id or any(c.candidate_id == user.faculty.id for c in adj.candidates)


@router.post("")
def create(body: AdjustmentIn, user: User = Depends(get_current_user), fac: Faculty = Depends(current_faculty),
           db: Session = Depends(get_db)):
    created = service.create_adjustments(db, fac, user, body.date, body.periods, body.reason)
    return [adjustment_dict(a) for a in created]


@router.get("/mine")
def mine(fac: Faculty = Depends(current_faculty), db: Session = Depends(get_db)):
    requested = (
        db.query(Adjustment).filter(Adjustment.requester_id == fac.id)
        .order_by(Adjustment.date.desc(), Adjustment.id.desc()).limit(30).all()
    )
    incoming = (
        db.query(AdjustmentCandidate)
        .filter(AdjustmentCandidate.candidate_id == fac.id,
                AdjustmentCandidate.state.in_(("requested", "accepted")))
        .order_by(AdjustmentCandidate.id.desc()).limit(30).all()
    )
    return {
        "requested": [adjustment_dict(a) for a in requested],
        "incoming": [incoming_request_dict(c) for c in incoming],
    }


@router.get("")
def list_all(user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    rows = db.query(Adjustment).order_by(Adjustment.date.desc(), Adjustment.id.desc()).limit(100).all()
    return [adjustment_dict(a) for a in rows]


@router.get("/token/{token}")
def token_view(token: str, db: Session = Depends(get_db), _=Depends(token_respond_limit)):
    """Landing page for the email links (no login). Showing it never changes anything."""
    cand = service.candidate_for_token(db, token)
    return incoming_request_dict(cand) | {
        "candidate_name": cand.candidate.name,
        "used": cand.token_used_at is not None,
        "adjustment_status": cand.adjustment.status,
    }


@router.post("/respond-token", dependencies=[Depends(token_respond_limit)])
def respond_token(body: TokenRespondIn, db: Session = Depends(get_db)):
    return service.respond_by_token(db, body.token, body.action)


@router.get("/{adjustment_id}")
def get_one(adjustment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adj = _adjustment(db, adjustment_id)
    if not _can_view(user, adj):
        raise HTTPException(status_code=403, detail="Not allowed")
    return adjustment_dict(adj)


@router.get("/{adjustment_id}/candidates")
def candidates(adjustment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adj = _adjustment(db, adjustment_id)
    if not _can_view(user, adj):
        raise HTTPException(status_code=403, detail="Not allowed")
    return adjustment_dict(adj)["candidates"]


@router.post("/{adjustment_id}/choose")
def choose(adjustment_id: int, body: ChooseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adj = _adjustment(db, adjustment_id)
    service.choose(db, adj, body.candidate_id, user)
    return adjustment_dict(adj)


@router.post("/{adjustment_id}/respond")
def respond(adjustment_id: int, body: RespondIn, user: User = Depends(get_current_user),
            fac: Faculty = Depends(current_faculty), db: Session = Depends(get_db)):
    adj = _adjustment(db, adjustment_id)
    cand = next((c for c in adj.candidates if c.candidate_id == fac.id and c.state == "requested"), None)
    if cand is None:
        raise HTTPException(status_code=409, detail="There is no open request for you on this class")
    return service.respond(db, cand, body.action, user)


@router.post("/{adjustment_id}/cancel")
def cancel(adjustment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adj = service.cancel(db, _adjustment(db, adjustment_id), user)
    return adjustment_dict(adj)


@router.get("/{adjustment_id}/free-faculty")
def free_faculty(adjustment_id: int, user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    return service.free_faculty(db, _adjustment(db, adjustment_id))


@router.post("/{adjustment_id}/override")
def override(adjustment_id: int, body: OverrideIn, user: User = Depends(require_role("hod")),
             db: Session = Depends(get_db)):
    adj = service.override(db, _adjustment(db, adjustment_id), body.faculty_id, user, body.note)
    return adjustment_dict(adj)
