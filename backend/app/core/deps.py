"""Authentication / authorization dependencies. Authorization is always enforced here, server side."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import SESSION_COOKIE, decode_session_token
from app.modules.identity.models import Role, User


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthorized("Please sign in.")
    claims = decode_session_token(token)
    if not claims:
        raise Unauthorized("Your session has expired. Please sign in again.")
    user = db.get(User, int(claims["sub"]))
    if not user or not user.is_active or user.token_version != claims.get("tv"):
        raise Unauthorized("Your session is no longer valid. Please sign in again.")
    request.state.user_id = user.id
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    allowed = {r.value for r in roles}

    def _dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise Forbidden("Your role does not have access to this resource.")
        return user

    return _dep


farmer_only = require_roles(Role.FARMER)
provider_only = require_roles(Role.PROVIDER)
buyer_only = require_roles(Role.BUYER)
reviewer_only = require_roles(Role.REVIEWER)
admin_only = require_roles(Role.ADMIN)
