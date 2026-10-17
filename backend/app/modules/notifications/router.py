from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.db import get_db
from app.core.deps import current_user
from app.core.errors import NotFound
from app.core.pagination import PageParams, paginate
from app.modules.identity.models import User
from app.modules.notifications.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


def notification_out(n: Notification) -> dict:
    return {
        "id": n.id,
        "event_type": n.event_type,
        "title": n.title,
        "body": n.body,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "link": n.link,
        "severity": n.severity,
        "read_at": n.read_at,
        "created_at": n.created_at,
    }


@router.get("")
def list_notifications(
    unread: bool = False,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc(), Notification.id.desc())
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    page = paginate(db, stmt, params, notification_out)
    page["unread_count"] = db.scalar(
        select(func.count(Notification.id)).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return page


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise NotFound("Notification not found.")
    if n.read_at is None:
        n.read_at = now_utc()
        db.commit()
    return notification_out(n)


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(current_user)):
    res = db.execute(
        update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)).values(read_at=now_utc())
    )
    db.commit()
    return {"updated": res.rowcount}
