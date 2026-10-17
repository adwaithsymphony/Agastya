"""Audit trail and notification helpers.

Both write inside the caller's transaction, so an event is only persisted if the change it
describes is committed. Notifications are created from real application events only.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.identity.models import User
from app.modules.notifications.models import Notification


def audit(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    summary: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    severity: str = "info",
) -> AuditEvent:
    ev = AuditEvent(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        before=before,
        after=after,
        severity=severity,
    )
    db.add(ev)
    return ev


def org_user_ids(db: Session, organization_id: int | None, role: str | None = None) -> list[int]:
    if organization_id is None:
        return []
    stmt = select(User.id).where(User.organization_id == organization_id, User.is_active.is_(True))
    if role:
        stmt = stmt.where(User.role == role)
    return list(db.scalars(stmt))


def role_user_ids(db: Session, role: str) -> list[int]:
    return list(db.scalars(select(User.id).where(User.role == role, User.is_active.is_(True))))


def notify(
    db: Session,
    user_ids: Iterable[int],
    *,
    event_type: str,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    link: str | None = None,
    severity: str = "info",
    exclude_user_id: int | None = None,
) -> int:
    n = 0
    for uid in dict.fromkeys(user_ids):
        if uid == exclude_user_id:
            continue
        db.add(
            Notification(
                user_id=uid,
                event_type=event_type,
                title=title,
                body=body,
                entity_type=entity_type,
                entity_id=entity_id,
                link=link,
                severity=severity,
            )
        )
        n += 1
    return n
