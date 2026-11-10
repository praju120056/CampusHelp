from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import _now

# "adjusted" records a class handed to someone else (weight 0 by default).
LOG_TYPES = ("theory", "lab", "duty", "meeting", "substitution", "adjusted")


class WorkLog(Base):
    __tablename__ = "work_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[str] = mapped_column(String(20))
    topic: Mapped[str] = mapped_column(String(200), default="")
    units: Mapped[float] = mapped_column(Float, default=1.0)  # periods, slots or hours
    weight: Mapped[float] = mapped_column(Float, default=0.0)  # units × weight at save time (snapshot)
    period: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    source_slot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("timetable_slots.id"), nullable=True)
    tag: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    adjustment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("adjustments.id"), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    faculty = relationship("Faculty")


class LogDay(Base):
    """Marks that a faculty member submitted their log for a date (drives the HOD 'logged' status)."""

    __tablename__ = "log_days"
    __table_args__ = (UniqueConstraint("faculty_id", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
