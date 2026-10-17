from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONType, Timestamped


class AuditEvent(Timestamped, Base):
    __tablename__ = "audit_events"
    __table_args__ = (sa.Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSONType)
    after: Mapped[dict | None] = mapped_column(JSONType)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="info")

    actor = relationship("User", lazy="joined")


class IdempotencyRecord(Timestamped, Base):
    """Stores the response of a state-changing request so a retried request is not applied twice."""

    __tablename__ = "idempotency_records"
    __table_args__ = (sa.UniqueConstraint("user_id", "key", "scope", name="uq_idempotency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONType, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
