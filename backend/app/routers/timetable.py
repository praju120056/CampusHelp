from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Faculty, User
from app.routers.deps import current_faculty
from app.services import adjustments as adjustment_service
from app.services import clock, importer
from app.services import timetable as tt
from app.services.auth import get_current_user, require_role

router = APIRouter(prefix="/timetable", tags=["timetable"])


@router.get("/me")
def my_day(date: Optional[date] = None, fac: Faculty = Depends(current_faculty), db: Session = Depends(get_db)):
    return adjustment_service.my_classes(db, fac, date or clock.today())


@router.get("/day")
def day_grid(date: Optional[date] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return tt.section_grid(db, date or clock.today())


@router.get("/periods")
def periods():
    return {"periods": tt.PERIOD_TIMES, "day_periods": tt.DAY_PERIODS}


@router.get("/template.xlsx")
def template(user: User = Depends(require_role("hod"))):
    return Response(
        content=importer.template_workbook(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="timetable-template.xlsx"'},
    )


@router.post("/import")
async def import_timetable(
    file: UploadFile = File(...),
    commit: bool = Form(False),
    create_missing: bool = Form(False),
    user: User = Depends(require_role("hod")),
    db: Session = Depends(get_db),
):
    data = await file.read(10 * 1024 * 1024)
    return importer.import_timetable(db, data, commit=commit, create_missing=create_missing)
