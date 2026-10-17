"""Double-submit CSRF protection for cookie-authenticated, state-changing requests."""
from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
EXEMPT_PATHS = {"/api/v1/auth/login"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            request.method not in SAFE_METHODS
            and request.url.path.startswith("/api/")
            and request.url.path not in EXEMPT_PATHS
            and request.cookies.get(SESSION_COOKIE)
        ):
            cookie = request.cookies.get(CSRF_COOKIE, "")
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not header or not hmac.compare_digest(cookie, header):
                return JSONResponse(
                    {"error": {"code": "csrf_failed", "message": "Security token missing or invalid. Refresh and try again.", "details": None}},
                    status_code=403,
                )
        return await call_next(request)
