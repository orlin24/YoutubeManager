"""Authenticated YouTube API clients + error mapping."""
from __future__ import annotations

from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.youtube_account import YouTubeAccount
from app.services.encryption import decrypt_str
from app.utils.errors import AppError
from app.utils.logging import get_logger

logger = get_logger("youtube.client")

AUTH_EXPIRED_MSG = (
    "Akses YouTube bermasalah (token tidak valid / izin kurang). "
    "Hubungkan ulang akun ini di halaman Channels."
)


def _build_credentials(db: Session, account: YouTubeAccount) -> Credentials:
    s = get_settings()
    try:
        access = decrypt_str(account.access_token_encrypted)
        refresh = (
            decrypt_str(account.refresh_token_encrypted) if account.refresh_token_encrypted else None
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Token decryption failed", exc_info=exc)
        raise AppError(401, "YOUTUBE_AUTH_EXPIRED", AUTH_EXPIRED_MSG) from exc

    if not access:
        raise AppError(401, "YOUTUBE_AUTH_EXPIRED", AUTH_EXPIRED_MSG)

    # This google-auth version compares creds.expiry against a NAIVE utcnow().
    # Convert the stored expiry to the true UTC instant, then drop tzinfo.
    # (Never naive-ize the wall-clock time directly - that shifts the instant by
    # the local offset and makes the token look valid for hours after expiry.)
    expiry = account.token_expiry
    if expiry is not None:
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)  # best-effort for legacy rows
        expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

    creds = Credentials(
        token=access,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=s.GOOGLE_CLIENT_ID,
        client_secret=s.GOOGLE_CLIENT_SECRET,
        expiry=expiry,  # without this, google-auth never refreshes
    )

    # Refresh if expired (or expiry unknown - e.g. rows from before this fix)
    if refresh and (not creds.valid or creds.expired or account.token_expiry is None):
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001
            logger.error("Token refresh failed", exc_info=exc)
            account.auth_error = (
                "Gagal memperbarui token Google (mungkin di-revoke atau izin diubah). "
                "Klik Connect ulang di halaman Channels."
            )
            db.commit()
            raise AppError(401, "YOUTUBE_AUTH_EXPIRED", AUTH_EXPIRED_MSG) from exc
        from app.services.encryption import encrypt_str

        account.access_token_encrypted = encrypt_str(creds.token or "")
        if creds.expiry:
            # google-auth stores naive-UTC expiry; store the real UTC instant
            stored = creds.expiry if creds.expiry.tzinfo else creds.expiry.replace(tzinfo=timezone.utc)
            account.token_expiry = stored
        account.auth_error = None  # refresh worked - connection is healthy
        db.commit()
    return creds


_REQUEST_TIMEOUT = 600  # seconds per HTTP request (stalled chunk -> timeout -> retry/pause)


def _authorized_http(creds):
    """httplib2 with a timeout so a stalled upload/API call fails instead of
    hanging forever (the resumable session then pauses and can be resumed)."""
    import httplib2

    from google_auth_httplib2 import AuthorizedHttp

    # follow_redirects=False: YouTube's resumable upload answers each chunk
    # with 308 (Resume Incomplete, no Location). httplib2 wrongly treats
    # 308 as a redirect and raises RedirectMissingLocation - disabling
    # redirect-following lets googleapiclient handle 308 correctly.
    http = httplib2.Http(timeout=_REQUEST_TIMEOUT)
    http.follow_redirects = False
    return AuthorizedHttp(creds, http=http)


def get_authenticated_client(db: Session, account: YouTubeAccount):
    """Returns a YouTube Data API v3 service."""
    creds = _build_credentials(db, account)
    return build("youtube", "v3", http=_authorized_http(creds))


def get_analytics_client(db: Session, account: YouTubeAccount):
    """Returns a YouTube Analytics API v2 service."""
    creds = _build_credentials(db, account)
    return build("youtubeAnalytics", "v2", http=_authorized_http(creds))


def map_google_error(exc: HttpError) -> AppError:
    status = exc.resp.status if exc.resp is not None else 0
    body = exc.content.decode("utf-8", "ignore") if exc.content else ""
    reason = ""
    try:
        import json

        reason = json.loads(body).get("error", {}).get("errors", [{}])[0].get("reason", "")
    except Exception:  # noqa: BLE001
        pass

    if status == 401 or reason == "unauthorized" or reason == "invalidCredentials":
        return AppError(401, "YOUTUBE_AUTH_EXPIRED", AUTH_EXPIRED_MSG)
    if status == 403 and reason in ("insufficientPermissions", "forbidden", "commentThreadsDisabled"):
        return AppError(
            403, "YOUTUBE_PERMISSION",
            "Izin YouTube kurang untuk komentar. Hubungkan ulang akun ini di halaman Channels "
            "(setelah update, token otomatis memuat izin komentar).",
        )
    if status == 403 and "quota" in reason.lower():
        return AppError(429, "YOUTUBE_QUOTA", "YouTube API quota exceeded. Please try again later.")
    if status == 429 or reason in ("rateLimitExceeded", "quotaExceeded"):
        return AppError(
            429, "YOUTUBE_QUOTA",
            "Kuota API YouTube untuk hari ini habis (dipakai sync + fitur lain). "
            "Coba lagi besok, atau naikkan kuota di Google Cloud Console.",
        )
    if status == 404:
        return AppError(404, "YOUTUBE_NOT_FOUND", "The requested YouTube resource was not found.")
    if status == 403:
        return AppError(403, "YOUTUBE_PERMISSION", "YouTube denied this operation due to permissions.")
    if status == 500 or status >= 502:
        return AppError(503, "YOUTUBE_UNAVAILABLE", "YouTube API is temporarily unavailable.")
    return AppError(502, "YOUTUBE_API_ERROR", "YouTube API error.")


def safe_call(fn, *args, **kwargs):
    """Wrap a google client method call, mapping errors to AppError."""
    try:
        return fn(*args, **kwargs).execute()
    except HttpError as exc:
        raise map_google_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        # google.auth RefreshError and friends escape as plain exceptions when
        # the stored credentials cannot be refreshed.
        if exc.__class__.__name__ == "RefreshError" or "refresh" in exc.__class__.__name__.lower():
            raise AppError(401, "YOUTUBE_AUTH_EXPIRED", AUTH_EXPIRED_MSG) from exc
        raise
