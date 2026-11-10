"""Workload Fairness Analytics (A5, A8–A10)."""
import calendar
import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Faculty
from app.services import clock, workload
from app.services.settings_store import get_setting


def gini(values: list[float]) -> float:
    """0 = everyone carries the same load; values toward 1 = load concentrated on a few people."""
    n = len(values)
    total = sum(values)
    if n == 0 or total <= 0:
        return 0.0
    mean = total / n
    diff_sum = sum(abs(a - b) for a in values for b in values)
    return diff_sum / (2 * n * n * mean)


def mean_sd(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return mean, sd


def classify(value: float, mean: float, sd: float) -> str:
    """A9: above mean + 1 SD = overloaded, below mean − 1 SD = underused."""
    if sd <= 1e-9:
        return "normal"
    if value > mean + sd:
        return "overloaded"
    if value < mean - sd:
        return "underused"
    return "normal"


def score_from_gini(g: float) -> float:
    """0–100, higher is fairer. One decimal, so a single day's log visibly moves it."""
    return round((1 - g) * 100, 1)


def longest_run(flags: list[str], wanted: str = "overloaded") -> int:
    best = run = 0
    for flag in flags:
        run = run + 1 if flag == wanted else 0
        best = max(best, run)
    return best


def rolling_windows(end: date, count: int, days: int = 7) -> list[tuple[date, date]]:
    """`count` back-to-back windows of `days` days ending on `end`, oldest first."""
    out = []
    for i in range(count):
        w_end = end - timedelta(days=days * i)
        out.append((w_end - timedelta(days=days - 1), w_end))
    return list(reversed(out))


def fairness_report(db: Session, end: Optional[date] = None) -> dict:
    cfg = get_setting(db, "fairness")
    days = int(cfg["window_days"])
    trend_n = max(int(cfg["trend_weeks"]), 4)
    burnout_n = int(cfg["burnout_weeks"])
    end = end or clock.today()
    w = workload.weights(db)
    faculty = db.query(Faculty).order_by(Faculty.id).all()

    windows = rolling_windows(end, trend_n, days)
    stats = []
    for start, w_end in windows:
        loads = workload.weighted_loads(db, start, w_end, w)
        values = [loads.get(f.id, 0.0) for f in faculty]
        m, sd = mean_sd(values)
        stats.append({"start": start, "end": w_end, "loads": loads, "gini": gini(values), "mean": m, "sd": sd})

    current = stats[-1]
    last4 = stats[-4:]
    units_now = workload.units_by_type(db, current["start"], current["end"])
    rows = []
    for fac in faculty:
        weeks = [
            {
                "start": s["start"].isoformat(),
                "end": s["end"].isoformat(),
                "load": round(s["loads"].get(fac.id, 0.0), 1),
                "flag": classify(s["loads"].get(fac.id, 0.0), s["mean"], s["sd"]),
            }
            for s in last4
        ]
        load = current["loads"].get(fac.id, 0.0)
        by_type = units_now.get(fac.id, {})
        rows.append(
            {
                "faculty_id": fac.id,
                "name": fac.name,
                "designation": fac.designation,
                "load": round(load, 1),
                "flag": classify(load, current["mean"], current["sd"]),
                "weeks": weeks,
                "burnout": longest_run([wk["flag"] for wk in weeks]) >= burnout_n,
                "substitutions": by_type.get("substitution", 0.0),
                "duties": by_type.get("duty", 0.0),
            }
        )
    return {
        "window": {"start": current["start"].isoformat(), "end": current["end"].isoformat(), "days": days},
        "score": score_from_gini(current["gini"]),
        "gini": round(current["gini"], 3),
        "mean": round(current["mean"], 2),
        "sd": round(current["sd"], 2),
        "upper": round(current["mean"] + current["sd"], 2),
        "lower": round(max(0.0, current["mean"] - current["sd"]), 2),
        "faculty": rows,
        "trend": [
            {
                "start": s["start"].isoformat(),
                "end": s["end"].isoformat(),
                # A window with no logs at all has no meaningful score.
                "score": score_from_gini(s["gini"]) if s["mean"] > 0 else None,
                "gini": round(s["gini"], 3) if s["mean"] > 0 else None,
                "mean": round(s["mean"], 2),
            }
            for s in stats[-int(cfg["trend_weeks"]):]
        ],
        "counts": {
            "overloaded": sum(1 for r in rows if r["flag"] == "overloaded"),
            "underused": sum(1 for r in rows if r["flag"] == "underused"),
            "burnout": sum(1 for r in rows if r["burnout"]),
        },
        "weights": w,
        "burnout_weeks": burnout_n,
    }


def _calendar_periods(end: date, granularity: str, count: int) -> list[tuple[str, date, date]]:
    out = []
    if granularity == "month":
        y, m = end.year, end.month
        for _ in range(count):
            last = calendar.monthrange(y, m)[1]
            out.append((date(y, m, 1).strftime("%b %Y"), date(y, m, 1), date(y, m, last)))
            m -= 1
            if m == 0:
                y, m = y - 1, 12
    else:
        monday = end - timedelta(days=end.weekday())
        for i in range(count):
            start = monday - timedelta(weeks=i)
            out.append((f"Wk of {start:%d %b}", start, start + timedelta(days=6)))
    return list(reversed(out))


def load_series(db: Session, granularity: str = "week", count: int = 8, end: Optional[date] = None) -> dict:
    """A5: weekly or monthly weighted load per faculty and for the department."""
    end = end or clock.today()
    w = workload.weights(db)
    faculty = db.query(Faculty).order_by(Faculty.id).all()
    periods = _calendar_periods(end, granularity, count)
    per_period = [workload.weighted_loads(db, start, stop, w) for _, start, stop in periods]
    return {
        "granularity": granularity,
        "periods": [{"label": label, "start": s.isoformat(), "end": e.isoformat()} for label, s, e in periods],
        "faculty": [
            {"faculty_id": f.id, "name": f.name, "values": [round(p.get(f.id, 0.0), 1) for p in per_period]}
            for f in faculty
        ],
        "department": [round(sum(p.values()), 1) for p in per_period],
        "mean": [round(sum(p.values()) / len(faculty), 1) if faculty else 0 for p in per_period],
    }
