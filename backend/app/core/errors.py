"""Consistent error responses: {"error": {"code", "message", "details"}}."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("agastya")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class InvalidTransition(AppError):
    status_code = 409
    code = "invalid_transition"


class Unprocessable(AppError):
    status_code = 422
    code = "validation_error"


def _body(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def _dev() -> bool:
    """Setup hints are only shown outside production."""
    from app.core.config import get_settings

    return not get_settings().is_production


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error"
        )
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse(_body("validation_error", "Some fields need attention.", details), status_code=422)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        log.warning("integrity error: %s", exc.orig.__class__.__name__)
        return JSONResponse(
            _body("conflict", "This change conflicts with existing records."), status_code=409
        )

    @app.exception_handler(OperationalError)
    async def _operational(_: Request, exc: OperationalError):
        log.error(
    "Database operational error: %s",
    str(exc.orig),
    exc_info=True,
)
        message = "The service is temporarily unavailable. Please try again shortly."
        if _dev():
            message = "The database is unreachable. Check that it is running and that DATABASE_URL in .env is correct."
        return JSONResponse(_body("service_unavailable", message), status_code=503)

    @app.exception_handler(ProgrammingError)
    async def _programming_error(_: Request, exc: ProgrammingError):
        # A missing/out-of-date schema commonly surfaces on the first query as a 500.
        # Keep internals in server logs, but give local developers a safe next step.
        log.exception("database programming error; check migrations and SQL", exc_info=exc)
        message = "The service is temporarily unavailable. Please try again shortly."
        if _dev():
            message = "The database schema is missing or out of date. From the backend folder run `alembic upgrade head`, then `python -m app.doctor`."
        return JSONResponse(_body("database_schema_error", message), status_code=503)

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(_: Request, exc: SQLAlchemyError):
        log.exception("database operation failed", exc_info=exc)
        message = "The service is temporarily unavailable. Please try again shortly."
        if _dev():
            message = "A database operation failed. Check the backend terminal and run `python -m app.doctor`."
        return JSONResponse(_body("database_error", message), status_code=503)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(_body("internal_error", "Something went wrong. Please try again."), status_code=500)
