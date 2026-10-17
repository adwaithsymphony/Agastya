"""Single source of 'now' so tests can freeze time."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_frozen: datetime | None = None


def now_utc() -> datetime:
    return _frozen if _frozen is not None else datetime.now(timezone.utc)


def freeze(at: datetime | None) -> None:
    global _frozen
    _frozen = at


def local_today(tz: str) -> date:
    return now_utc().astimezone(ZoneInfo(tz)).date()
