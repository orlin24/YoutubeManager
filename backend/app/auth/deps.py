"""Auth dependencies for FastAPI routers."""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.jwt import decode_token
from app.database import get_db
from app.models.user import User
from app.utils.errors import AppError


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token: str | None = None
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get("aym_access")
    if not token:
        raise AppError(401, "UNAUTHORIZED", "Authentication required.")
    payload = decode_token(token, expected_type="access")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise AppError(401, "UNAUTHORIZED", "User not found.")
    return user
