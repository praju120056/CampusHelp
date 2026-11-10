"""Weighted workload (A3). Weights always come from settings, so changing them changes every load."""
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import WorkLog
from app.services import clock
from app.services.settings_store import get_setting


def weights(db: Session) -> dict:
    return get_setting(db, "workload_weights")


def units_by_type(db: Session, start: date, end: date) -> dict[int, dict[str, float]]:
    rows = (
        db.query(WorkLog.faculty_id, WorkLog.type, func.sum(WorkLog.units))
        .filter(WorkLog.date >= start, WorkLog.date <= end)
        .group_by(WorkLog.faculty_id, WorkLog.type)
        .all()
    )
    out: dict[int, dict[str, float]] = defaultdict(dict)
    for fid, typ, units in rows:
        out[fid][typ] = float(units or 0)
    return out


def weighted_loads(db: Session, start: date, end: date, w: Optional[dict] = None) -> dict[int, float]:
    w = w or weights(db)
    loads: dict[int, float] = defaultdict(float)
    for fid, by_type in units_by_type(db, start, end).items():
        for typ, units in by_type.items():
            loads[fid] += units * float(w.get(typ, 0.0))
    return dict(loads)


def recent_window(d: date) -> tuple[date, date]:
    """The 7 days before d (or before today, for future dates): the load used to rank substitutes."""
    end = min(d, clock.today()) - timedelta(days=1)
    return end - timedelta(days=6), end


def recent_loads(db: Session, d: date) -> dict[int, float]:
    start, end = recent_window(d)
    return weighted_loads(db, start, end)
