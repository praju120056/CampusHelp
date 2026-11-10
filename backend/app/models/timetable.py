from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

SLOT_TYPES = ("theory", "lab")


class TimetableSlot(Base):
    """One period of the weekly timetable. day: 0=Mon … 5=Sat. A 2-period lab is two rows."""

    __tablename__ = "timetable_slots"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id"), index=True)
    section: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(80))
    day: Mapped[int] = mapped_column(Integer)
    period: Mapped[int] = mapped_column(Integer)
    room_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(10), default="theory")

    faculty = relationship("Faculty")
    room = relationship("Location")


class Leave(Base):
    __tablename__ = "leaves"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = whole day
    reason: Mapped[str] = mapped_column(String(200), default="")


class Duty(Base):
    """Invigilation and other duty slots (block the faculty member for that period)."""

    __tablename__ = "duties"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(60), default="Invigilation")
