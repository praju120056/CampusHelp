"""Daily work log (A1, A2, A4, A7)."""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Duty, Faculty, LogDay, TimetableSlot, User, WorkLog
from app.models.logs import LOG_TYPES
from app.services import audit, clock
from app.services.events import broker
from app.services.settings_store import get_setting
from app.services.timetable import ALL_PERIODS, DayView, periods_label

TYPE_LABELS = {
    "theory": "Theory class",
    "lab": "Lab",
    "duty": "Duty",
    "meeting": "Meeting / committee",
    "substitution": "Substitution",
    "adjusted": "Class handed over",
}


class LogError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _entry_from_log(log: WorkLog) -> dict:
    return {
        "id": log.id,
        "type": log.type,
        "topic": log.topic,
        "units": log.units,
        "period": log.period,
        "section": log.section,
        "subject": log.subject,
        "source_slot_id": log.source_slot_id,
        "adjustment_id": log.adjustment_id,
        "tag": log.tag,
        "saved": True,
        "locked": log.tag == "adjustment",
    }


def _when(entry: dict) -> str:
    period = entry["period"]
    if not period:
        return ""
    if entry["type"] in ("theory", "lab", "substitution", "adjusted"):
        last = min(max(ALL_PERIODS), period + max(1, round(entry["units"])) - 1)
        return periods_label(list(range(period, last + 1)))
    return f"P{period}"


def prefill(db: Session, faculty: Faculty, d: date) -> dict:
    """A2: the day's entries, pre-filled from the timetable (after adjustments) and duties."""
    existing = db.query(WorkLog).filter(WorkLog.faculty_id == faculty.id, WorkLog.date == d).all()
    submission = db.query(LogDay).filter(LogDay.faculty_id == faculty.id, LogDay.date == d).first()
    entries = [_entry_from_log(log) for log in existing]

    if submission is None:
        view = DayView(db, d)
        covered_slots = {log.source_slot_id for log in existing if log.source_slot_id}
        covered_adjustments = {log.adjustment_id for log in existing if log.adjustment_id}
        covered_duty_periods = {log.period for log in existing if log.type == "duty"}
        for periods, a in view.units_of(faculty.id):
            if a.adjustment_id and a.adjustment_id in covered_adjustments:
                continue
            if a.slot_id and a.kind == "regular" and a.slot_id in covered_slots:
                continue
            entries.append(
                {
                    "id": None,
                    "type": "substitution" if a.kind == "substitute" else a.type,
                    "topic": "",
                    "units": float(len(periods)),
                    "period": periods[0],
                    "section": a.section,
                    "subject": a.subject,
                    "source_slot_id": a.slot_id if a.kind == "regular" else None,
                    "adjustment_id": a.adjustment_id,
                    "tag": "adjustment" if a.adjustment_id else None,
                    "saved": False,
                    "locked": False,
                }
            )
        for duty in db.query(Duty).filter(Duty.faculty_id == faculty.id, Duty.date == d).all():
            if duty.period in covered_duty_periods:
                continue
            entries.append(
                {
                    "id": None,
                    "type": "duty",
                    "topic": duty.kind,
                    "units": 1.0,
                    "period": duty.period,
                    "section": None,
                    "subject": None,
                    "source_slot_id": None,
                    "adjustment_id": None,
                    "tag": None,
                    "saved": False,
                    "locked": False,
                }
            )
    entries.sort(key=lambda e: (e["period"] is None, e["period"] or 0, e["type"]))
    for e in entries:
        e["when"] = _when(e)
    return {
        "date": d.isoformat(),
        "submitted": submission is not None,
        "submitted_at": submission.submitted_at.isoformat() if submission else None,
        "entries": entries,
        "weights": get_setting(db, "workload_weights"),
        "type_labels": TYPE_LABELS,
    }


def submit_day(db: Session, faculty: Faculty, user: User, d: date, entries: list[dict]) -> dict:
    """Save the whole day: update, add, and remove entries. Every change goes to the audit log (A7)."""
    if d > clock.today():
        raise LogError("You can't log a future date")
    weights = get_setting(db, "workload_weights")
    existing = {log.id: log for log in db.query(WorkLog).filter(WorkLog.faculty_id == faculty.id, WorkLog.date == d)}
    keep: set[int] = set()

    for raw in entries:
        typ = raw.get("type")
        if typ not in LOG_TYPES:
            raise LogError(f"Unknown entry type: {typ}")
        try:
            units = float(raw.get("units") or 1)
        except (TypeError, ValueError):
            raise LogError("Units must be a number")
        if not 0 < units <= 12:
            raise LogError("Units must be between 0 and 12")
        topic = (raw.get("topic") or "").strip()[:200]
        log_id = raw.get("id")

        if log_id and log_id in existing:
            log = existing[log_id]
            keep.add(log.id)
            changes = {}
            if log.topic != topic:
                changes["topic"] = [log.topic, topic]
                log.topic = topic
            if log.tag != "adjustment":  # adjustment entries are set by the system; only the topic is editable
                if log.type != typ:
                    changes["type"] = [log.type, typ]
                    log.type = typ
                if log.units != units:
                    changes["units"] = [log.units, units]
                    log.units = units
            log.weight = log.units * float(weights.get(log.type, 0))
            if changes:
                log.updated_at = clock.now()
                audit.record(db, user.id, "work_log", log.id, "update", changes)
            continue

        slot_id = raw.get("source_slot_id")
        if slot_id:
            slot = db.get(TimetableSlot, slot_id)
            if slot is None or slot.faculty_id != faculty.id:
                slot_id = None
        log = WorkLog(
            faculty_id=faculty.id,
            date=d,
            type=typ,
            topic=topic,
            units=units,
            weight=units * float(weights.get(typ, 0)),
            period=raw.get("period"),
            section=(raw.get("section") or None),
            subject=(raw.get("subject") or None),
            source_slot_id=slot_id,
            created_by=user.id,
        )
        db.add(log)
        db.flush()
        keep.add(log.id)
        audit.record(db, user.id, "work_log", log.id, "create", {"type": typ, "units": units, "topic": topic})

    for log_id, log in existing.items():
        if log_id not in keep and log.tag != "adjustment":
            audit.record(db, user.id, "work_log", log.id, "delete", {"type": log.type, "units": log.units})
            db.delete(log)

    submission = db.query(LogDay).filter(LogDay.faculty_id == faculty.id, LogDay.date == d).first()
    if submission is None:
        db.add(LogDay(faculty_id=faculty.id, date=d, submitted_at=clock.now()))
    else:
        submission.submitted_at = clock.now()
    db.commit()
    broker.publish("logs", "log.saved", {"faculty_id": faculty.id, "date": d.isoformat()})
    return prefill(db, faculty, d)


def today_status(db: Session, d: Optional[date] = None) -> dict:
    """A4: per-faculty logged / not logged for a date, plus the reminder list."""
    d = d or clock.today()
    submitted = {row.faculty_id: row.submitted_at for row in db.query(LogDay).filter(LogDay.date == d)}
    counts: dict[int, int] = {}
    for log in db.query(WorkLog).filter(WorkLog.date == d):
        counts[log.faculty_id] = counts.get(log.faculty_id, 0) + 1
    view = DayView(db, d)
    rows = []
    for fac in db.query(Faculty).order_by(Faculty.id).all():
        rows.append(
            {
                "faculty_id": fac.id,
                "name": fac.name,
                "designation": fac.designation,
                "logged": fac.id in submitted,
                "submitted_at": submitted[fac.id].isoformat() if fac.id in submitted else None,
                "entries": counts.get(fac.id, 0),
                "classes_today": len(view.units_of(fac.id)),
            }
        )
    return {
        "date": d.isoformat(),
        "faculty": rows,
        "logged": sum(1 for r in rows if r["logged"]),
        "not_logged": [r for r in rows if not r["logged"]],
    }


def send_reminders(db: Session, d: Optional[date] = None) -> int:
    from app.services.notify import notify_user

    status = today_status(db, d)
    for row in status["not_logged"]:
        fac = db.get(Faculty, row["faculty_id"])
        notify_user(db, fac.user, "Please log today's work", f"Your work log for {status['date']} is not submitted yet.", link="/log")
    db.commit()
    return len(status["not_logged"])
