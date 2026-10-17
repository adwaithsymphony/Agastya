from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JSONType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(sa.types.TypeDecorator):
    """Timezone-aware timestamps on every backend: stored as UTC, always returned aware (UTC)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


def enum_check(column: str, values) -> sa.CheckConstraint:
    vals = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{column} IN ({vals})", name=f"{column}_valid")


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs = {"pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = sa.create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @sa.event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):  # pragma: no cover - sqlite only
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

        _SessionLocal = sessionmaker(bind=_engine, autoflush=True, expire_on_commit=False)
    return _engine


def set_engine(engine) -> None:
    """Used by tests to point the app at a dedicated database."""
    global _engine, _SessionLocal
    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


def SessionLocal() -> Session:  # noqa: N802
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_status() -> dict:
    """Connectivity and migration state. Never raises; never includes credentials or driver messages."""
    import logging

    from sqlalchemy import inspect

    import app.models  # noqa: F401 - make sure every table is registered

    state = {"available": False, "schema_ready": False, "missing_tables": []}
    try:
        names = set(inspect(get_engine()).get_table_names())
        state["available"] = True
        state["missing_tables"] = sorted(set(Base.metadata.tables) - names)
        state["schema_ready"] = not state["missing_tables"]
    except Exception as exc:  # pragma: no cover - depends on the environment
        logging.getLogger("agastya").warning("database check failed: %s", type(exc).__name__)
    return state
