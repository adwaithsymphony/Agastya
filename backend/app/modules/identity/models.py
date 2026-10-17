from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamped, enum_check, UTCDateTime


class Role(StrEnum):
    FARMER = "farmer"
    PROVIDER = "provider"
    BUYER = "buyer"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class OrgKind(StrEnum):
    FARM = "farm"
    PROVIDER = "provider"
    BUYER = "buyer"
    AGENCY = "agency"
    PLATFORM = "platform"


class Organization(Timestamped, Base):
    __tablename__ = "organizations"
    __table_args__ = (enum_check("kind", [k.value for k in OrgKind]),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class User(Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (enum_check("role", [r.value for r in Role]),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=sa.false())
    preferred_language: Mapped[str] = mapped_column(String(2), nullable=False, default="en", server_default="en")

    organization: Mapped[Organization | None] = relationship(lazy="joined")
