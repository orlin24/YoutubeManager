"""Security headers middleware + CSRF origin check."""
from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import get_settings
from app.utils.errors import AppError


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Cache-Control"] = "no-store"
        return response


def check_csrf(request: Request) -> None:
    """Defense-in-depth CSRF check for cookie-authenticated mutating requests.

    SameSite=Lax already blocks cross-site POSTs; this additionally verifies the
    Origin header against the allowed origins when one is present.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not request.cookies.get("aym_access"):
        return  # no cookie auth -> CSRF not applicable
    origin = request.headers.get("origin")
    if not origin:
        return  # non-browser clients
    allowed = get_settings().origins
    if origin not in allowed:
        raise AppError(403, "FORBIDDEN", "Cross-origin request rejected.")
