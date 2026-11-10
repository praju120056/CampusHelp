from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.services import clock, exports, fairness
from app.services import logs as log_service
from app.services.auth import require_role

router = APIRouter(tags=["analytics"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _range(start: Optional[date], end: Optional[date]) -> tuple[date, date]:
    end = end or clock.today()
    return start or end - timedelta(days=6), end


@router.get("/analytics/today")
def today(date: Optional[date] = None, user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    return log_service.today_status(db, date)


@router.post("/analytics/remind")
def remind(user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    return {"reminded": log_service.send_reminders(db)}


@router.get("/analytics/fairness")
def fairness_view(end: Optional[date] = None, user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    return fairness.fairness_report(db, end)


@router.get("/analytics/load")
def load(granularity: Literal["week", "month"] = "week", count: int = 8,
         user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    return fairness.load_series(db, granularity, max(1, min(count, 24)))


@router.get("/exports/logs.xlsx")
def export_logs(start: Optional[date] = None, end: Optional[date] = None,
                user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    s, e = _range(start, end)
    return Response(content=exports.logs_workbook(db, s, e), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="work-logs_{s}_{e}.xlsx"'})


@router.get("/exports/report.xlsx")
def export_report(start: Optional[date] = None, end: Optional[date] = None,
                  user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    s, e = _range(start, end)
    return Response(content=exports.report_workbook(db, s, e), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="naac-nba-report_{s}_{e}.xlsx"'})


@router.get("/exports/report.json")
def report_json(start: Optional[date] = None, end: Optional[date] = None,
                user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    """Data for the printable report page (browser 'Save as PDF' gives the PDF)."""
    s, e = _range(start, end)
    return exports.report_data(db, s, e)
