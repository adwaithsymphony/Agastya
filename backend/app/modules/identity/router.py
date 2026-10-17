from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import current_user
from app.core.errors import AppError, Unauthorized
from app.core.events import audit
from app.core.security import (
    CSRF_COOKIE,
    DUMMY_HASH,
    SESSION_COOKIE,
    create_session_token,
    hash_password,
    new_csrf_token,
    verify_password,
)
from app.modules.identity.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

_attempts: dict[str, deque] = defaultdict(deque)
_WINDOW, _MAX_ATTEMPTS = 300, 10


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    organization_id: int | None
    organization_name: str | None
    phone: str | None = None
    notify_email: bool = False
    preferred_language: str = "en"


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        role=u.role,
        organization_id=u.organization_id,
        organization_name=u.organization.name if u.organization else None,
        phone=u.phone,
        notify_email=u.notify_email,
        preferred_language=u.preferred_language,
    )


def _rate_limited(key: str) -> bool:
    q = _attempts[key]
    now = time.monotonic()
    while q and now - q[0] > _WINDOW:
        q.popleft()
    return len(q) >= _MAX_ATTEMPTS


def set_session_cookies(response: Response, user: User) -> None:
    s = get_settings()
    token, exp = create_session_token(user.id, user.token_version)
    max_age = s.session_ttl_minutes * 60
    response.set_cookie(
        SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=s.cookie_secure, samesite="lax", path="/"
    )
    response.set_cookie(
        CSRF_COOKIE, new_csrf_token(), max_age=max_age, httponly=False, secure=s.cookie_secure, samesite="lax", path="/"
    )


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{body.email}|{request.client.host if request.client else '-'}"
    if _rate_limited(key):
        raise AppError("Too many sign-in attempts. Please wait a few minutes.", code="rate_limited", status_code=429)
    user = db.scalar(select(User).where(User.email == body.email))
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not ok:
        _attempts[key].append(time.monotonic())
        raise Unauthorized("Email or password is incorrect.")
    if not user.is_active:
        # Only revealed after a correct password, so it does not help account enumeration.
        raise AppError("This account has been deactivated. Contact your administrator.", code="account_disabled", status_code=403)
    _attempts.pop(key, None)
    user.last_login_at = now_utc()
    db.commit()
    set_session_cookies(response, user)
    return user_out(user)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    notify_email: bool | None = None
    preferred_language: Literal["en", "ml", "ta", "pa", "hi"] | None = None


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    return user_out(user)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.current_password, user.password_hash):
        raise AppError("Current password is incorrect.", code="invalid_password", status_code=400)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit(db, actor_id=user.id, action="user.password_changed", entity_type="user", entity_id=user.id)
    db.commit()
    set_session_cookies(response, user)
    response.status_code = 204
    return response
