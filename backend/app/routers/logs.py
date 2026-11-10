from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Faculty, User, WorkLog
from app.routers.deps import current_faculty
from app.schemas.requests import LogDayIn
from app.services import clock
from app.services import logs as service
from app.services.auth import get_current_user

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/prefill")
def prefill(date: Optional[date] = None, fac: Faculty = Depends(current_faculty), db: Session = Depends(get_db)):
    return service.prefill(db, fac, date or clock.today())


@router.post("")
def submit(body: LogDayIn, user: User = Depends(get_current_user), fac: Faculty = Depends(current_faculty),
           db: Session = Depends(get_db)):
    return service.submit_day(db, fac, user, body.date, [e.model_dump() for e in body.entries])


@router.get("")
def list_logs(
    start: Optional[date] = None,
    end: Optional[date] = None,
    faculty_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    end = end or clock.today()
    start = start or end - timedelta(days=6)
    if user.role != "hod":
        if user.faculty is None:
            raise HTTPException(status_code=403, detail="Not allowed")
        faculty_id = user.faculty.id
    query = db.query(WorkLog).filter(WorkLog.date >= start, WorkLog.date <= end)
    if faculty_id:
        query = query.filter(WorkLog.faculty_id == faculty_id)
    rows = query.order_by(WorkLog.date.desc(), WorkLog.faculty_id, WorkLog.period).limit(2000).all()
    return [
        {
            "id": r.id, "date": r.date.isoformat(), "faculty_id": r.faculty_id, "faculty": r.faculty.name,
            "type": r.type, "topic": r.topic, "units": r.units, "weight": r.weight, "period": r.period,
            "section": r.section, "subject": r.subject, "tag": r.tag,
        }
        for r in rows
    ]
