"""Request bodies (validated by Pydantic)."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class TicketPatch(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    assigned_to: Optional[int] = None
    worker: Optional[str] = None
    note: Optional[str] = None
    rejection_reason: Optional[str] = None


class AdjustmentIn(BaseModel):
    date: date
    periods: list[int] = Field(min_length=1)
    reason: str = ""


class ChooseIn(BaseModel):
    candidate_id: int


class RespondIn(BaseModel):
    action: Literal["accept", "decline"]


class TokenRespondIn(BaseModel):
    token: str
    action: Literal["accept", "decline"]


class OverrideIn(BaseModel):
    faculty_id: int
    note: str = ""


class LogEntryIn(BaseModel):
    id: Optional[int] = None
    type: str
    topic: str = ""
    units: float = 1.0
    period: Optional[int] = None
    section: Optional[str] = None
    subject: Optional[str] = None
    source_slot_id: Optional[int] = None


class LogDayIn(BaseModel):
    date: date
    entries: list[LogEntryIn]


class SettingsIn(BaseModel):
    workload_weights: Optional[dict[str, float]] = None
    deadline_hours: Optional[dict[str, float]] = None
    demo_deadline_minutes: Optional[dict[str, float]] = None
    reminder: Optional[dict[str, float]] = None
    fairness: Optional[dict[str, float]] = None


class PdfImportIn(BaseModel):
    """A timetable draft the HOD has reviewed. `codes` may have been edited (code → name)."""

    draft: dict
    commit: bool = False
    create_missing: bool = True
    replace_all: bool = False
