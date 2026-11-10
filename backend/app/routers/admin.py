from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Notification, User
from app.schemas.requests import SettingsIn
from app.schemas.serializers import notification_dict
from app.services import settings_store
from app.services.auth import get_current_user, require_role

router = APIRouter(tags=["admin"])


@router.get("/health")
def health():
    s = get_settings()
    return {
        "ok": True,
        "gemini": bool(s.gemini_api_key),
        "gemini_model": s.gemini_model,
        "smtp": s.smtp_configured,
        "demo_mode": s.demo_mode,
    }


@router.get("/admin/settings")
def get_settings_view(user: User = Depends(require_role("hod", "estate")), db: Session = Depends(get_db)):
    return settings_store.all_settings(db)


@router.put("/admin/settings")
def put_settings(body: SettingsIn, user: User = Depends(require_role("hod")), db: Session = Depends(get_db)):
    try:
        for key, value in body.model_dump(exclude_none=True).items():
            settings_store.set_setting(db, key, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return settings_store.all_settings(db)


@router.get("/users")
def list_users(role: Optional[str] = None, user: User = Depends(require_role("hod", "incharge", "estate")),
               db: Session = Depends(get_db)):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    return [{"id": u.id, "name": u.name, "role": u.role} for u in query.order_by(User.id)]


@router.get("/notifications")
def my_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.channel == "in_app")
        .order_by(Notification.id.desc())
        .limit(50)
        .all()
    )
    return {"unread": sum(1 for n in rows if not n.read), "items": [notification_dict(n) for n in rows]}


@router.post("/notifications/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.read.is_(False)).update({"read": True})
    db.commit()
    return {"ok": True}


@router.get("/outbox")
def outbox(user: User = Depends(require_role("hod", "estate")), db: Session = Depends(get_db)):
    """B8: every email, whether sent, waiting in the outbox (SMTP off) or failed."""
    rows = db.query(Notification).filter(Notification.channel == "email").order_by(Notification.id.desc()).limit(200).all()
    return {"smtp_configured": get_settings().smtp_configured, "items": [notification_dict(n) for n in rows]}
