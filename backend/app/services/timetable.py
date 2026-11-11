"""Timetable for a given date, after accepted adjustments are applied.

DayView is the single source of truth for "is this faculty member free?". Every clash check
(candidate search, accept, HOD override, log prefill) goes through it."""
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Adjustment, Duty, Leave, TimetableSlot

# RNSIT CSE (AI&ML) bell times (tea break 11:10-11:30, lunch 1:20-2:05).
PERIOD_TIMES = {
    1: ("09:20", "10:15"),
    2: ("10:15", "11:10"),
    3: ("11:30", "12:25"),
    4: ("12:25", "13:20"),
    5: ("14:05", "15:00"),
    6: ("15:00", "15:55"),
    7: ("15:55", "16:50"),
}
ALL_PERIODS = tuple(PERIOD_TIMES)
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAY_PERIODS = {0: 7, 1: 7, 2: 7, 3: 7, 4: 7, 5: 4, 6: 0}  # Saturday is a half day


@dataclass(frozen=True)
class Assignment:
    faculty_id: int
    period: int
    section: str
    subject: str
    type: str
    room_id: Optional[int]
    slot_id: Optional[int]
    kind: str = "regular"  # regular | substitute | swap
    adjustment_id: Optional[int] = None
    original_faculty_id: Optional[int] = None
    batch: Optional[str] = None


def same_class_scope(a: "Assignment", b: "Assignment") -> bool:
    """True when two assignments in the same section and period are in conflict.
    Different batches run in parallel and co-teachers of one class share a subject; neither is a clash."""
    if a.subject == b.subject and a.batch == b.batch:
        return False
    return a.batch is None or b.batch is None or a.batch == b.batch


def periods_label(periods: list[int]) -> str:
    ps = sorted(periods)
    start, end = PERIOD_TIMES[ps[0]][0], PERIOD_TIMES[ps[-1]][1]
    name = f"P{ps[0]}" if len(ps) == 1 else f"P{ps[0]}–P{ps[-1]}"
    return f"{name} ({start}–{end})"


def apply_adjustment(items: list[Assignment], adj: Adjustment, cand) -> list[Assignment]:
    """Return the day's assignments with one accepted adjustment applied."""
    wanted = set(adj.periods)
    to_cand = [i for i, a in enumerate(items) if a.faculty_id == adj.requester_id and a.period in wanted]
    moved: list[Assignment] = [
        replace(items[i], faculty_id=cand.candidate_id, kind=cand.kind, adjustment_id=adj.id, original_faculty_id=adj.requester_id)
        for i in to_cand
    ]
    to_req: list[int] = []
    if cand.kind == "swap":
        swap = set(cand.swap_periods or [])
        to_req = [
            i
            for i, a in enumerate(items)
            if a.faculty_id == cand.candidate_id and a.period in swap and a.section == adj.section
        ]
        moved += [
            replace(items[i], faculty_id=adj.requester_id, kind="swap", adjustment_id=adj.id, original_faculty_id=cand.candidate_id)
            for i in to_req
        ]
    drop = set(to_cand) | set(to_req)
    return [a for i, a in enumerate(items) if i not in drop] + moved


def day_assignments(db: Session, d: date, exclude_adjustment_id: Optional[int] = None) -> list[Assignment]:
    slots = db.query(TimetableSlot).filter(TimetableSlot.day == d.weekday()).all()
    items = [
        Assignment(s.faculty_id, s.period, s.section, s.subject, s.type, s.room_id, s.id, batch=s.batch)
        for s in slots
    ]
    accepted = (
        db.query(Adjustment)
        .filter(Adjustment.date == d, Adjustment.status == "accepted")
        .order_by(Adjustment.id)
        .all()
    )
    for adj in accepted:
        if adj.id == exclude_adjustment_id:
            continue
        cand = next((c for c in adj.candidates if c.state == "accepted"), None)
        if cand is not None:
            items = apply_adjustment(items, adj, cand)
    return items


def section_grid(db: Session, d: date) -> dict:
    """C6: the timetable for a date, sections × periods, with adjustments shown."""
    from app.models import Faculty

    names = {f.id: f.name for f in db.query(Faculty).all()}
    return DayView(db, d).section_grid(names)


class DayView:
    def __init__(self, db: Session, d: date, exclude_adjustment_id: Optional[int] = None) -> None:
        self.date = d
        self.items = day_assignments(db, d, exclude_adjustment_id)
        self.duties: dict[int, dict[int, str]] = defaultdict(dict)
        for duty in db.query(Duty).filter(Duty.date == d).all():
            self.duties[duty.faculty_id][duty.period] = duty.kind
        self.leaves: dict[int, set[int]] = defaultdict(set)
        for leave in db.query(Leave).filter(Leave.date == d).all():
            if leave.period is None:
                self.leaves[leave.faculty_id].update(ALL_PERIODS)
            else:
                self.leaves[leave.faculty_id].add(leave.period)

    def assignments_of(self, faculty_id: int) -> list[Assignment]:
        return sorted((a for a in self.items if a.faculty_id == faculty_id), key=lambda a: a.period)

    def busy(self, faculty_id: int) -> dict[int, str]:
        """period → why the faculty member is not free."""
        reasons: dict[int, str] = {}
        for a in self.assignments_of(faculty_id):
            reasons[a.period] = f"Class {a.section} {a.subject}"
        for period, kind in self.duties.get(faculty_id, {}).items():
            reasons.setdefault(period, f"Duty: {kind}")
        for period in self.leaves.get(faculty_id, set()):
            reasons.setdefault(period, "On leave")
        return reasons

    def is_free(self, faculty_id: int, periods) -> bool:
        busy = self.busy(faculty_id)
        return not any(p in busy for p in periods)

    def units_of(self, faculty_id: int) -> list[tuple[list[int], Assignment]]:
        """The faculty member's classes as units: consecutive lab periods (same section/subject) form one unit."""
        units: list[tuple[list[int], Assignment]] = []
        for a in self.assignments_of(faculty_id):
            if units:
                periods, first = units[-1]
                if (
                    a.type == "lab"
                    and first.type == "lab"
                    and a.section == first.section
                    and a.subject == first.subject
                    and a.batch == first.batch
                    and a.kind == first.kind
                    and a.period == periods[-1] + 1
                ):
                    periods.append(a.period)
                    continue
            units.append(([a.period], a))
        return units

    def unit_at(self, faculty_id: int, period: int) -> Optional[tuple[list[int], Assignment]]:
        for periods, first in self.units_of(faculty_id):
            if period in periods:
                return periods, first
        return None

    def section_grid(self, names: dict[int, str]) -> dict:
        sections = sorted({a.section for a in self.items})
        n_periods = DAY_PERIODS[self.date.weekday()]
        cells: dict[str, dict[int, dict]] = {s: {} for s in sections}
        for a in self.items:
            label = f"{a.subject} ({a.batch})" if a.batch else a.subject
            faculty = names.get(a.faculty_id, "?")
            cell = cells[a.section].get(a.period)
            if cell is not None:  # parallel batches / co-teachers share one cell
                cell["subject"] = cell["subject"] if label in cell["subject"].split(" / ") else f"{cell['subject']} / {label}"
                if faculty not in cell["faculty"].split(", "):
                    cell["faculty"] += f", {faculty}"
                continue
            cells[a.section][a.period] = {
                "subject": label,
                "type": a.type,
                "faculty": faculty,
                "kind": a.kind,
                "original_faculty": names.get(a.original_faculty_id) if a.original_faculty_id else None,
            }
        return {
            "date": self.date.isoformat(),
            "day": DAY_NAMES[self.date.weekday()],
            "periods": [{"period": p, "start": PERIOD_TIMES[p][0], "end": PERIOD_TIMES[p][1]} for p in range(1, n_periods + 1)],
            "sections": [{"section": s, "cells": {str(p): c for p, c in cells[s].items()}} for s in sections],
        }

    def clashes(self) -> set[tuple[int, int, str]]:
        """Every (faculty_id, period, problem) where someone is double-booked."""
        found: set[tuple[int, int, str]] = set()
        count: dict[tuple[int, int], int] = defaultdict(int)
        for a in self.items:
            count[(a.faculty_id, a.period)] += 1
        for (fid, period), n in count.items():
            if n > 1:
                found.add((fid, period, "two classes"))
            if period in self.duties.get(fid, {}):
                found.add((fid, period, "class during duty"))
            if period in self.leaves.get(fid, set()):
                found.add((fid, period, "class during leave"))
        sections: dict[tuple[str, int], list[Assignment]] = defaultdict(list)
        for a in self.items:
            sections[(a.section, a.period)].append(a)
        for (section, period), group in sections.items():
            if any(same_class_scope(x, y) for i, x in enumerate(group) for y in group[i + 1:]):
                found.add((-1, period, f"section {section} double-booked"))
        return found
