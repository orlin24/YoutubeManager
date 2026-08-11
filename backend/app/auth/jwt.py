"""JWT encode/decode for access + refresh tokens (HS256, PyJWT)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings
from app.utils.errors import AppError

_ALGO = "HS256"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def encode_access_token(user_id: str) -> str:
    s = get_settings()
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": _now(),
        "exp": _now() + timedelta(minutes=s.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, s.effective_secret_key, algorithm=_ALGO)


def encode_refresh_token(user_id: str) -> str:
    s = get_settings()
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": _now(),
        "exp": _now() + timedelta(days=s.REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, s.effective_secret_key, algorithm=_ALGO)


def decode_token(token: str, expected_type: str = "access") -> dict:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.effective_secret_key, algorithms=[_ALGO])
    except jwt.PyJWTError as exc:
        raise AppError(401, "UNAUTHORIZED", "Invalid or expired session.") from exc
    if payload.get("type") != expected_type:
        raise AppError(401, "UNAUTHORIZED", "Invalid token type.")
    return payload
