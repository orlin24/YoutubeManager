"""Application error type + helpers to render the standard error envelope."""
from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Raise to produce the standard error envelope."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def error_body(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))


def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    msg = first.get("msg", "Invalid request")
    loc = first.get("loc", [])
    if loc:
        msg = f"{'.'.join(str(x) for x in loc)}: {msg}"
    return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", msg))


def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    import logging

    logging.getLogger("app").error("Unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500, content=error_body("INTERNAL_ERROR", "An unexpected error occurred.")
    )
