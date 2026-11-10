from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas.requests import LoginIn
from app.schemas.serializers import user_dict
from app.services.auth import authenticate, create_token, get_current_user
from app.services.ratelimit import login_limit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", dependencies=[Depends(login_limit)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return {"token": create_token(user), "user": user_dict(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_dict(user)
