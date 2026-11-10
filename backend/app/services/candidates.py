"""Candidate search for a class adjustment (C3, C4).

Order: 1) swaps within the same section, 2) free qualified substitutes, 3) free but not qualified
(fallback). Within each group, lowest recent weighted load first. Every candidate is checked with
DayView, so no suggestion can double-book anyone."""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Adjustment, AdjustmentCandidate, Faculty
from app.services import workload
from app.services.timetable import DayView, periods_label

FIT_LOAD_PENALTY = 2.0  # fit points lost per unit of recent weighted load
FIT_SUB_PENALTY = 5.0  # fit points lost per recent substitution
FIT_FORMULA = "100 − 2 × weekly load − 5 × recent substitutions"
TIER = {"swap": 0, "substitute": 1, "fallback": 2}


@dataclass
class Suggestion:
    faculty: Faculty
    kind: str  # swap | substitute
    tier: int
    fit: float
    load: float
    recent_subs: int
    breakdown: dict = field(default_factory=dict)
    swap_periods: Optional[list[int]] = None
    swap_subject: Optional[str] = None
    swap_type: Optional[str] = None


def subject_matches(faculty: Faculty, subject: str) -> bool:
    base = subject.removesuffix(" Lab").strip()
    qualified = set(faculty.qualified_subjects or [])
    return subject in qualified or base in qualified


def recent_substitution_counts(db: Session, d: date) -> dict[int, int]:
    """Accepted substitutions in the 30 days around d (C4 'number of recent substitutions')."""
    rows = (
        db.query(AdjustmentCandidate.candidate_id)
        .join(Adjustment, Adjustment.id == AdjustmentCandidate.adjustment_id)
        .filter(
            AdjustmentCandidate.state == "accepted",
            AdjustmentCandidate.kind == "substitute",
            Adjustment.status == "accepted",
            Adjustment.date >= d - timedelta(days=30),
            Adjustment.date <= d + timedelta(days=7),
        )
        .all()
    )
    counts: dict[int, int] = defaultdict(int)
    for (fid,) in rows:
        counts[fid] += 1
    return counts


def find_candidates(db: Session, adj: Adjustment, view: Optional[DayView] = None) -> list[Suggestion]:
    view = view or DayView(db, adj.date, exclude_adjustment_id=adj.id)
    periods = sorted(adj.periods)
    loads = workload.recent_loads(db, adj.date)
    subs = recent_substitution_counts(db, adj.date)
    out: list[Suggestion] = []

    for fac in db.query(Faculty).order_by(Faculty.id).all():
        if fac.id == adj.requester_id or not view.is_free(fac.id, periods):
            continue
        load = round(loads.get(fac.id, 0.0), 1)
        recent = subs.get(fac.id, 0)
        fit = max(0.0, round(100 - FIT_LOAD_PENALTY * load - FIT_SUB_PENALTY * recent, 1))
        common = {
            "free": True,
            "free_note": f"Free in {periods_label(periods)}",
            "weekly_load": load,
            "recent_substitutions": recent,
            "fit_formula": FIT_FORMULA,
        }

        # 1) Swap: the candidate teaches the same section today in a unit of the same length,
        #    and the requester is free then. Both sides are clash-checked.
        for unit_periods, unit in view.units_of(fac.id):
            if unit.section != adj.section or len(unit_periods) != len(periods):
                continue
            if set(unit_periods) & set(periods) or not view.is_free(adj.requester_id, unit_periods):
                continue
            out.append(
                Suggestion(
                    faculty=fac,
                    kind="swap",
                    tier=TIER["swap"],
                    fit=fit,
                    load=load,
                    recent_subs=recent,
                    swap_periods=list(unit_periods),
                    swap_subject=unit.subject,
                    swap_type=unit.type,
                    breakdown=common
                    | {
                        "subject_match": None,
                        "swap_note": f"They take {adj.section} {adj.subject} in {periods_label(periods)}; "
                        f"you take their {unit.section} {unit.subject} in {periods_label(unit_periods)}",
                    },
                )
            )

        # 2) / 3) Free substitute.
        qualified = subject_matches(fac, adj.subject)
        out.append(
            Suggestion(
                faculty=fac,
                kind="substitute",
                tier=TIER["substitute"] if qualified else TIER["fallback"],
                fit=fit,
                load=load,
                recent_subs=recent,
                breakdown=common | {"subject_match": qualified},
            )
        )

    out.sort(key=lambda s: (s.tier, s.load, s.recent_subs, s.faculty.id))
    return out


def store_candidates(db: Session, adj: Adjustment) -> list[AdjustmentCandidate]:
    rows = []
    for rank, s in enumerate(find_candidates(db, adj), start=1):
        row = AdjustmentCandidate(
            adjustment_id=adj.id,
            candidate_id=s.faculty.id,
            kind=s.kind,
            rank=rank,
            score=s.fit,
            score_breakdown=s.breakdown | {"tier": s.tier},
            swap_periods=s.swap_periods,
            swap_subject=s.swap_subject,
            swap_type=s.swap_type,
            state="suggested",
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows
