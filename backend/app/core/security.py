"""Password hashing (scrypt, stdlib) and signed session tokens (JWT, HS256)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

_N, _R, _P, _DKLEN = 2**15, 8, 1, 64
_MAXMEM = 128 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, n, r, p, salt, dk = encoded.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk)
        got = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=_MAXMEM,
        )
        return hmac.compare_digest(got, expected)
    except (ValueError, TypeError):
        return False


# A pre-computed hash so login timing is similar for unknown users.
DUMMY_HASH = hash_password(secrets.token_urlsafe(12))

SESSION_COOKIE = "agastya_session"
CSRF_COOKIE = "agastya_csrf"
CSRF_HEADER = "x-csrf-token"


def create_session_token(user_id: int, token_version: int) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=s.session_ttl_minutes)
    token = jwt.encode(
        {"sub": str(user_id), "tv": token_version, "iat": now, "exp": exp, "jti": secrets.token_hex(8)},
        s.secret_key,
        algorithm="HS256",
    )
    return token, exp


def decode_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
