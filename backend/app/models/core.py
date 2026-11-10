from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.services import clock

ROLES = ("faculty", "hod", "incharge", "estate")


def _now() -> datetime:
    return clock.now()


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    dept_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)

    faculty: Mapped[Optional["Faculty"]] = relationship(back_populates="user", uselist=False)


class Faculty(Base):
    __tablename__ = "faculty"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    designation: Mapped[str] = mapped_column(String(80), default="Assistant Professor")
    qualified_subjects: Mapped[list] = mapped_column(JSON, default=list)

    user: Mapped[User] = relationship(back_populates="faculty")

    @property
    def name(self) -> str:
        return self.user.name


class Setting(Base):
    """Configurable values (workload weights, ticket deadlines). Defaults live in services/settings_store."""

    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Notification(Base):
    """In-app messages (channel=in_app) and emails (channel=email; status sent/outbox/failed/queued)."""

    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(10))
    to_addr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    status: Mapped[str] = mapped_column(String(10))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
