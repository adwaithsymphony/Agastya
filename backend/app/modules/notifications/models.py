from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamped, UTCDateTime


class Notification(Timestamped, Base):
    __tablename__ = "notifications"
    __table_args__ = (sa.Index("ix_notifications_user_unread", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    link: Mapped[str | None] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="info")
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
