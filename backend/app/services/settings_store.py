"""Configurable values. Defaults below (from spec A3 / B7) are seeded into the settings table;
logic always reads through get_setting(), never hard-codes these numbers."""
import copy

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Setting

DEFAULTS: dict = {
    # A3: weight per unit. theory/lab/substitution per period, duty per slot, meeting per hour.
    "workload_weights": {
        "theory": 1.0,
        "lab": 1.5,
        "duty": 1.0,
        "meeting": 0.5,
        "substitution": 1.0,
        "adjusted": 0.0,
    },
    # B7: hours to resolve, per priority.
    "deadline_hours": {"critical": 4, "high": 24, "normal": 72},
    # B7 demo mode: the same deadlines in minutes, so escalation can be shown on stage.
    "demo_deadline_minutes": {"critical": 2, "high": 5, "normal": 10},
    # Send the pre-deadline reminder once this fraction of the time has passed.
    "reminder": {"fraction": 0.75},
    # A8–A10.
    "fairness": {"window_days": 7, "trend_weeks": 4, "burnout_weeks": 3},
}

EDITABLE = ("workload_weights", "deadline_hours", "demo_deadline_minutes", "reminder", "fairness")


def get_setting(db: Session, key: str) -> dict:
    default = copy.deepcopy(DEFAULTS[key])
    row = db.get(Setting, key)
    if row is None:
        return default
    merged = default
    merged.update(row.value or {})
    return merged


def set_setting(db: Session, key: str, value: dict) -> dict:
    if key not in EDITABLE:
        raise ValueError(f"Unknown setting: {key}")
    allowed = DEFAULTS[key].keys()
    clean = {}
    for k, v in value.items():
        if k not in allowed:
            raise ValueError(f"Unknown field '{k}' in {key}")
        try:
            num = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{key}.{k} must be a number")
        if num < 0:
            raise ValueError(f"{key}.{k} cannot be negative")
        clean[k] = num
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value={})
        db.add(row)
    merged = dict(row.value or {})
    merged.update(clean)
    row.value = merged
    return get_setting(db, key) | merged


def all_settings(db: Session) -> dict:
    return {k: get_setting(db, k) for k in EDITABLE} | {"demo_mode": get_settings().demo_mode}


def seed_defaults(db: Session) -> None:
    for key, value in DEFAULTS.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=copy.deepcopy(value)))
