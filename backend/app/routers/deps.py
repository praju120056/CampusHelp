from fastapi import Depends, HTTPException

from app.models import Faculty, User
from app.services.auth import get_current_user

STAFF = ("faculty", "hod", "incharge", "estate")
TICKET_STAFF = ("hod", "incharge", "estate")


def current_faculty(user: User = Depends(get_current_user)) -> Faculty:
    if user.faculty is None:
        raise HTTPException(status_code=403, detail="Only faculty members can do this")
    return user.faculty
