from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import _now

# open: suggestions shown · pending: waiting on a candidate · accepted · exhausted: nobody left · cancelled
ADJ_STATUSES = ("open", "pending", "accepted", "exhausted", "cancelled")
# suggested → requested → accepted | declined ; unavailable = no longer free when checked again
CAND_STATES = ("suggested", "requested", "accepted", "declined", "unavailable", "withdrawn")


class Adjustment(Base):
    """One class unit (a period, or a whole lab block) the requester cannot take."""

    __tablename__ = "adjustments"
    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("faculty.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    periods: Mapped[list] = mapped_column(JSON)
    section: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(80))
    slot_type: Mapped[str] = mapped_column(String(10), default="theory")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(15), default="open")
    chosen_candidate_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    overridden_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    requester = relationship("Faculty", foreign_keys=[requester_id])
    candidates = relationship(
        "AdjustmentCandidate", back_populates="adjustment", order_by="AdjustmentCandidate.rank"
    )


class AdjustmentCandidate(Base):
    __tablename__ = "adjustment_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    adjustment_id: Mapped[int] = mapped_column(ForeignKey("adjustments.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("faculty.id"))
    kind: Mapped[str] = mapped_column(String(12))  # swap | substitute
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    swap_periods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # candidate's periods given to requester
    swap_subject: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    swap_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    state: Mapped[str] = mapped_column(String(15), default="suggested")
    token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    token_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    adjustment = relationship("Adjustment", back_populates="candidates")
    candidate = relationship("Faculty")
