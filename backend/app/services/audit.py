from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    user_id: Optional[int],
    entity: str,
    entity_id: int,
    action: str,
    detail: Optional[dict] = None,
) -> None:
    db.add(AuditLog(user_id=user_id, entity=entity, entity_id=entity_id, action=action, detail=detail))
