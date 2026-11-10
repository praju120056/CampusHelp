"""Single source of "now", so tests can move time. Always call clock.now(), never datetime.now().

Times are local, timezone-naive (one laptop, one campus)."""
from datetime import date, datetime


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def today() -> date:
    return now().date()
