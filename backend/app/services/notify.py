"""Notifications: in-app always; email via SMTP when configured, otherwise written to the outbox.

Emails are sent on a background thread after the database transaction commits, so a slow or
failing SMTP server never blocks or breaks a request."""
import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from typing import Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from app import db as db_module
from app.config import get_settings
from app.models import Notification, User

log = logging.getLogger("educrew.notify")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="smtp")
_PENDING_KEY = "pending_emails"


def absolute_link(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return get_settings().public_base_url.rstrip("/") + path


def notify_user(
    db: Session,
    user: User,
    subject: str,
    body: str,
    link: Optional[str] = None,
    email: bool = True,
) -> None:
    db.add(Notification(user_id=user.id, channel="in_app", subject=subject, body=body, link=link, status="unread"))
    if email and user.email:
        queue_email(db, user.email, subject, body, link, user_id=user.id)


def notify_role(db: Session, role: str, subject: str, body: str, link: Optional[str] = None) -> None:
    for user in db.query(User).filter(User.role == role).all():
        notify_user(db, user, subject, body, link)


def queue_email(
    db: Session,
    to_addr: str,
    subject: str,
    body: str,
    link: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Notification:
    settings = get_settings()
    full_link = absolute_link(link)
    text = body + (f"\n\nOpen: {full_link}" if full_link else "") + "\n\n— EduCrew"
    note = Notification(
        user_id=user_id,
        channel="email",
        to_addr=to_addr,
        subject=subject,
        body=text,
        link=link,
        status="queued" if settings.smtp_configured else "outbox",
    )
    db.add(note)
    db.flush()
    if settings.smtp_configured:
        db.info.setdefault(_PENDING_KEY, []).append((note.id, to_addr, subject, text))
    return note


@event.listens_for(Session, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING_KEY, [])
    for item in pending:
        _executor.submit(_send, *item)


@event.listens_for(Session, "after_rollback")
def _drop_after_rollback(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)


def _send(notification_id: int, to_addr: str, subject: str, text: str) -> None:
    settings = get_settings()
    status, error = "sent", None
    try:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(text)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001 — any SMTP failure falls back to the outbox
        status, error = "failed", f"{type(exc).__name__}: {exc}"[:500]
        log.warning("Email to %s failed (%s); kept in outbox", to_addr, type(exc).__name__)
    db = db_module.SessionLocal()
    try:
        note = db.get(Notification, notification_id)
        if note is not None:
            note.status = status
            note.error = error
            db.commit()
    finally:
        db.close()
