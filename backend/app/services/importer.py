"""Timetable import from Excel (C2), with validation and name anonymisation.

Until the real RNSIT file arrives, this reads a simple "one row per period" layout:
    Faculty | Day | Period | Section | Subject | Type | Room
(Type = theory or lab; Room = a location code such as BLK-A-F1-R101, optional.)
Real names are replaced by "Faculty N". The name map is kept in data/faculty_name_map.csv,
which is gitignored. Adapt parse_rows() once the real layout is known."""
import csv
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from app.config import REPO_DIR
from app.models import Faculty, Location, TimetableSlot, User, WorkLog
from app.services.auth import hash_password
from app.services.timetable import DAY_PERIODS

NAME_MAP_PATH = REPO_DIR / "data" / "faculty_name_map.csv"
COLUMNS = ["Faculty", "Day", "Period", "Section", "Subject", "Type", "Room"]
DAYS = {"mon": 0, "monday": 0, "tue": 1, "tuesday": 1, "wed": 2, "wednesday": 2, "thu": 3, "thursday": 3,
        "fri": 4, "friday": 4, "sat": 5, "saturday": 5}


@dataclass
class ImportReport:
    rows_read: int = 0
    slots: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    new_faculty: list[str] = field(default_factory=list)
    committed: bool = False

    def as_dict(self) -> dict:
        return {
            "rows_read": self.rows_read,
            "valid_slots": len(self.slots),
            "errors": self.errors,
            "warnings": self.warnings,
            "new_faculty": self.new_faculty,
            "committed": self.committed,
        }


def template_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Timetable"
    ws.append(COLUMNS)
    ws.append(["Dr. Example Name", "Mon", 1, "5A", "Machine Learning", "theory", "BLK-A-F1-R101"])
    ws.append(["Dr. Example Name", "Tue", 3, "5A", "Machine Learning Lab", "lab", "BLK-A-F1-LAB105"])
    ws.append(["Dr. Example Name", "Tue", 4, "5A", "Machine Learning Lab", "lab", "BLK-A-F1-LAB105"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def load_name_map(path: Optional[Path] = None) -> dict[str, str]:
    path = path or NAME_MAP_PATH  # looked up at call time, so tests can redirect it
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {row["real_name"]: row["anon_name"] for row in csv.DictReader(fh)}


def save_name_map(mapping: dict[str, str], path: Optional[Path] = None) -> None:
    path = path or NAME_MAP_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["real_name", "anon_name"])
        writer.writeheader()
        for real, anon in sorted(mapping.items(), key=lambda kv: int(kv[1].split()[-1])):
            writer.writerow({"real_name": real, "anon_name": anon})


def _anon_name(real: str, mapping: dict[str, str], existing_anon: set[str]) -> str:
    if real in mapping:
        return mapping[real]
    n = 1
    while f"Faculty {n}" in existing_anon or f"Faculty {n}" in mapping.values():
        n += 1
    mapping[real] = f"Faculty {n}"
    return mapping[real]


def parse_rows(data: bytes) -> tuple[list[dict], list[str]]:
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], ["The sheet is empty"]
    header = [str(c or "").strip().lower() for c in rows[0]]
    missing = [c for c in COLUMNS if c.lower() not in header and c != "Room"]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Expected: {', '.join(COLUMNS)}"]
    idx = {c: header.index(c.lower()) for c in COLUMNS if c.lower() in header}
    parsed = []
    for n, row in enumerate(rows[1:], start=2):
        if not any(row):
            continue
        parsed.append({"line": n} | {c: (row[i] if i < len(row) else None) for c, i in idx.items()})
    return parsed, []


def validate(db: Session, data: bytes, create_missing: bool = False) -> tuple[ImportReport, dict[str, str]]:
    report = ImportReport()
    rows, errors = parse_rows(data)
    report.errors += errors
    report.rows_read = len(rows)
    mapping = load_name_map()
    existing_anon = {u.name for u in db.query(User).filter(User.role.in_(("faculty", "hod")))}
    rooms = {loc.code: loc.id for loc in db.query(Location)}
    seen_fac: dict[tuple, int] = {}
    seen_sec: dict[tuple, int] = {}

    for row in rows:
        line = row["line"]
        real = str(row.get("Faculty") or "").strip()
        section = str(row.get("Section") or "").strip()
        subject = str(row.get("Subject") or "").strip()
        typ = str(row.get("Type") or "theory").strip().lower()
        day = DAYS.get(str(row.get("Day") or "").strip().lower())
        try:
            period = int(row.get("Period"))
        except (TypeError, ValueError):
            period = None
        if not real or not section or not subject:
            report.errors.append(f"Row {line}: missing faculty, section or subject")
            continue
        if day is None:
            report.errors.append(f"Row {line}: unknown day '{row.get('Day')}'")
            continue
        if period is None or not 1 <= period <= DAY_PERIODS[day]:
            report.errors.append(f"Row {line}: period must be 1–{DAY_PERIODS[day]} on that day")
            continue
        if typ not in ("theory", "lab"):
            report.errors.append(f"Row {line}: type must be theory or lab")
            continue
        room_code = str(row.get("Room") or "").strip()
        room_id: Optional[int] = None
        if room_code:
            room_id = rooms.get(room_code)
            if room_id is None:
                report.warnings.append(f"Row {line}: unknown room '{room_code}' (left blank)")
        known = real in mapping and mapping[real] in existing_anon
        anon: Optional[str] = None
        if known or create_missing:
            anon = _anon_name(real, mapping, existing_anon)
            if not known and anon not in report.new_faculty:
                report.new_faculty.append(anon)
        else:
            report.errors.append(f"Row {line}: unknown faculty (not in the name map). Tick 'create missing faculty' to add.")
        # Clash checks run for every row, so one report lists every problem. Real names are never echoed.
        who = anon or "this faculty member"
        if (real, day, period) in seen_fac:
            report.errors.append(f"Row {line}: clash, {who} already teaches at this time (row {seen_fac[(real, day, period)]})")
            continue
        if (section, day, period) in seen_sec:
            report.errors.append(f"Row {line}: clash, section {section} already has a class (row {seen_sec[(section, day, period)]})")
            continue
        seen_fac[(real, day, period)] = line
        seen_sec[(section, day, period)] = line
        if anon is not None:
            report.slots.append({"faculty": anon, "section": section, "subject": subject, "day": day,
                                 "period": period, "type": typ, "room_id": room_id})
    return report, mapping


def import_timetable(db: Session, data: bytes, commit: bool, create_missing: bool = False) -> dict:
    report, mapping = validate(db, data, create_missing)
    if not commit or report.errors or not report.slots:
        return report.as_dict()
    by_name = {u.name: u for u in db.query(User).filter(User.role.in_(("faculty", "hod")))}
    password = hash_password("demo1234")
    for anon in report.new_faculty:
        n = anon.split()[-1]
        user = User(name=anon, email=f"faculty{n}@educrew.local", password_hash=password, role="faculty")
        db.add(user)
        db.flush()
        db.add(Faculty(user_id=user.id, designation="Assistant Professor", qualified_subjects=[]))
        by_name[anon] = user
    db.flush()
    # Past work logs stay; they just stop pointing at slots that are about to be replaced.
    db.query(WorkLog).filter(WorkLog.source_slot_id.isnot(None)).update({WorkLog.source_slot_id: None})
    db.query(TimetableSlot).delete()
    for slot in report.slots:
        fac = by_name[slot["faculty"]].faculty
        if slot["subject"].removesuffix(" Lab") not in (fac.qualified_subjects or []):
            fac.qualified_subjects = list(fac.qualified_subjects or []) + [slot["subject"].removesuffix(" Lab")]
        db.add(TimetableSlot(faculty_id=fac.id, section=slot["section"], subject=slot["subject"], day=slot["day"],
                             period=slot["period"], type=slot["type"], room_id=slot["room_id"]))
    db.commit()
    save_name_map(mapping)
    report.committed = True
    return report.as_dict()
