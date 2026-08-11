"""Auth endpoints: one-time setup, login, logout, me, Google OAuth."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.jwt import decode_token, encode_access_token, encode_refresh_token
from app.auth.password import hash_password, verify_password
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.youtube_account import YouTubeAccount
from app.routers.deps import user_channel_ids
from app.services.audit_service import log_audit
from app.services.oauth import get_google_auth_url, handle_oauth_callback
from app.utils.errors import AppError
from app.utils.logging import get_logger
from app.utils.rate_limit import rate_limit
from app.utils.security import check_csrf

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("auth")

login_rate = rate_limit(10, 60)
setup_rate = rate_limit(5, 60)


class SetupRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name}


def _set_auth_cookies(response: Response, user_id: str) -> None:
    s = get_settings()
    secure = s.is_production
    response.set_cookie(
        key="aym_access",
        value=encode_access_token(user_id),
        max_age=s.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        key="aym_refresh",
        value=encode_refresh_token(user_id),
        max_age=s.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/api/auth",
    )


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)) -> dict:
    """True when the app is freshly installed and needs the one-time admin setup."""
    count = db.query(User).count()
    return {"setup_required": count == 0}


@router.post("/setup", status_code=201)
def setup(payload: SetupRequest, request: Request, response: Response,
          db: Session = Depends(get_db), _: None = Depends(setup_rate)) -> dict:
    """One-time admin setup. Only works when no user exists yet."""
    check_csrf(request)
    if db.query(User).count() > 0:
        raise AppError(409, "ALREADY_SETUP", "Setup sudah selesai. Silakan login.")
    user = User(
        email=payload.email.lower(),
        name=payload.name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _set_auth_cookies(response, user.id)
    log_audit(db, user_id=user.id, action="user_setup", target=user.email, result="ok")
    return {"user": _user_dict(user), "access_token": encode_access_token(user.id)}


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response,
          db: Session = Depends(get_db), _: None = Depends(login_rate)) -> dict:
    check_csrf(request)
    user = db.query(User).filter_by(email=payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid email or password.")
    _set_auth_cookies(response, user.id)
    log_audit(db, user_id=user.id, action="user_login", target=user.email, result="ok")
    return {"user": _user_dict(user), "access_token": encode_access_token(user.id)}


@router.post("/refresh")
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """Exchange the refresh cookie for a fresh access token (silent re-login)."""
    check_csrf(request)
    raw = request.cookies.get("aym_refresh")
    if not raw:
        raise AppError(401, "SESSION_EXPIRED", "Sesi berakhir. Silakan login ulang.")
    try:
        payload = decode_token(raw, "refresh")
    except AppError as exc:
        raise AppError(401, "SESSION_EXPIRED", "Sesi berakhir. Silakan login ulang.") from exc
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise AppError(401, "SESSION_EXPIRED", "Pengguna tidak ditemukan.")
    _set_auth_cookies(response, user.id)
    return {"user": _user_dict(user)}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("aym_access", path="/")
    response.delete_cookie("aym_refresh", path="/api/auth")
    return {"success": True}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    accounts = (
        db.query(YouTubeAccount)
        .filter_by(user_id=user.id)
        .order_by(YouTubeAccount.created_at.desc())
        .all()
    )
    return {
        "user": _user_dict(user),
        "accounts": [
            {
                "id": a.id,
                "channel_id": a.channel_id,
                "channel_title": a.channel_title,
                "channel_thumbnail": a.channel_thumbnail,
                "google_account_email": a.google_account_email,
                "connected_at": a.created_at.isoformat() if a.created_at else None,
                "auth_error": a.auth_error,
            }
            for a in accounts
        ],
    }


@router.get("/google")
def google_login() -> RedirectResponse:
    url, state = get_google_auth_url()
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        key="aym_oauth_state",
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=get_settings().is_production,
        path="/api/auth",
    )
    return response


@router.get("/google/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None,
                          db: Session = Depends(get_db)) -> RedirectResponse:
    s = get_settings()
    frontend = s.FRONTEND_URL
    if not code:
        return RedirectResponse(url=f"{frontend}?error=google_auth_failed", status_code=302)

    # The callback happens in a fresh browser context: there is no session cookie
    # with the user id, so we can't enforce login here. We store the user id in
    # the state to tie the callback to a logged-in user, and require login first.
    expected_state = request.cookies.get("aym_oauth_state") if request else None

    # If the user opened the flow from a fresh browser without a session, we
    # cannot attach the account. Redirect with an error asking to log in first.
    if expected_state is None:
        return RedirectResponse(url=f"{frontend}?error=google_auth_requires_login", status_code=302)
    if state != expected_state:
        return RedirectResponse(url=f"{frontend}?error=google_auth_failed", status_code=302)

    # user_id is not carried by the redirect chain; require an authenticated
    # session. We reuse the access cookie if present.
    auth_header = request.headers.get("Authorization") or ""
    token = auth_header[7:] if auth_header.lower().startswith("bearer ") else request.cookies.get("aym_access")
    if not token:
        return RedirectResponse(url=f"{frontend}?error=google_auth_requires_login", status_code=302)
    from app.auth.jwt import decode_token

    try:
        payload = decode_token(token, expected_type="access")
    except AppError:
        return RedirectResponse(url=f"{frontend}?error=google_auth_requires_login", status_code=302)
    user_id = payload.get("sub")

    try:
        await handle_oauth_callback(db, code=code, state=state, expected_state=expected_state, user_id=user_id)
        return RedirectResponse(url=f"{frontend}?connected=1", status_code=302)
    except AppError as exc:
        logger.warning("OAuth callback failed: %s", exc.code)
        return RedirectResponse(url=f"{frontend}?error=google_auth_failed", status_code=302)
