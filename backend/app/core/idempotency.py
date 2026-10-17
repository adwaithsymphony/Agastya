"""Idempotency-Key support for important state-changing operations.

A client may send the same `Idempotency-Key` header when retrying; the stored response is
returned instead of applying the change again. Reusing a key with a different payload is rejected.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Unprocessable
from app.modules.audit.models import IdempotencyRecord


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(jsonable_encoder(payload), sort_keys=True).encode()).hexdigest()


def run_idempotent(
    db: Session,
    *,
    user_id: int,
    key: str | None,
    scope: str,
    payload: Any,
    action: Callable[[], Any],
) -> Any:
    """Execute `action` (which must NOT commit) and commit together with the idempotency record."""
    if not key:
        result = action()
        db.commit()
        return result
    if len(key) > 80:
        raise Unprocessable("Idempotency-Key is too long.")
    h = _hash(payload)
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key, IdempotencyRecord.scope == scope
        )
    )
    if existing:
        if existing.request_hash != h:
            raise Conflict("This Idempotency-Key was already used with a different request.", code="idempotency_mismatch")
        return existing.response_body
    result = action()
    body = jsonable_encoder(result)
    db.add(
        IdempotencyRecord(
            user_id=user_id, key=key, scope=scope, request_hash=h, response_status=200, response_body=body
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key, IdempotencyRecord.scope == scope
            )
        )
        if existing and existing.request_hash == h:
            return existing.response_body
        raise
    return body
