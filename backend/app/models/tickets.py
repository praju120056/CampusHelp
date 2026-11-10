from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import _now

CATEGORIES = ("electrical", "plumbing", "housekeeping", "it", "civil")
PRIORITIES = ("critical", "high", "normal")
STATUSES = ("new", "assigned", "in_progress", "resolved", "rejected")
OPEN_STATUSES = ("new", "assigned", "in_progress")


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    block: Mapped[str] = mapped_column(String(20))
    floor: Mapped[int] = mapped_column(Integer)
    room_name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="classroom")
    side: Mapped[str] = mapped_column(String(1), default="N")  # corridor side, a row on the grid map
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    map_shape_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    assets = relationship("Asset", back_populates="location")


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))

    location = relationship("Location", back_populates="assets")


class CategoryAssignee(Base):
    """Routing table: ticket category → responsible in-charge."""

    __tablename__ = "category_assignees"
    category: Mapped[str] = mapped_column(String(20), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user = relationship("User")


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(12), unique=True, index=True)  # public, unguessable id
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(15), default="new")
    description: Mapped[str] = mapped_column(Text)
    photo_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    summary: Mapped[str] = mapped_column(String(200), default="")
    ai_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ai_priority: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # gemini | rules
    reporter_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    reporter_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reporter_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    report_count: Mapped[int] = mapped_column(Integer, default=1)
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    worker: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime)
    reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duplicate_of: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    location = relationship("Location")
    assignee = relationship("User", foreign_keys=[assigned_to])
    events = relationship("TicketEvent", back_populates="ticket", order_by="TicketEvent.id")

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(40))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    ticket = relationship("Ticket", back_populates="events")
