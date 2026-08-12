"""Google OAuth 2.0 flow for connecting YouTube accounts."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.channel import Channel
from app.models.youtube_account import YouTubeAccount
from app.services.audit_service import log_audit
from app.services.encryption import encrypt_str
from app.utils.errors import AppError
from app.utils.logging import get_logger

logger = get_logger("oauth")

SCOPES = [
    # TIDAK sertakan openid/userinfo.email/profile: itu "Google Sign In" yang
    # WAJIB verifikasi aplikasi oleh Google (hard block disabled_client utk app
    # unverified, non-owner). Scope YouTube saja => warning "unverified app"
    # bisa dilewati (Advanced -> Go to app unsafe).
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    # NOTE: yt-analytics-monetary.readonly (restricted scope) is intentionally NOT
    # requested - it blocks new sign-ins for unverified apps with disabled_client.
]

NOT_CONFIGURED_MSG = (
    "Google OAuth is not configured. Please configure GOOGLE_CLIENT_ID and "
    "GOOGLE_CLIENT_SECRET."
)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://oauth2.googleapis.com/oauth2/v3/userinfo"
_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"


def get_google_auth_url() -> tuple[str, str]:
    """Returns (consent_url, state). Raises NOT_CONFIGURED when unconfigured."""
    s = get_settings()
    if not s.GOOGLE_CLIENT_ID or not s.GOOGLE_CLIENT_SECRET:
        raise AppError(503, "NOT_CONFIGURED", NOT_CONFIGURED_MSG)
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": s.GOOGLE_CLIENT_ID,
        "redirect_uri": s.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), state


async def handle_oauth_callback(
    db: Session, *, code: str, state: str, expected_state: str, user_id: str
) -> None:
    s = get_settings()
    if not s.GOOGLE_CLIENT_ID or not s.GOOGLE_CLIENT_SECRET:
        raise AppError(503, "NOT_CONFIGURED", NOT_CONFIGURED_MSG)
    if not state or state != expected_state:
        raise AppError(400, "INVALID_STATE", "OAuth state mismatch. Please try again.")

    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": s.GOOGLE_CLIENT_ID,
                "client_secret": s.GOOGLE_CLIENT_SECRET,
                "redirect_uri": s.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.error("Google token exchange failed: %s", token_resp.text[:300])
            raise AppError(502, "YOUTUBE_AUTH_EXPIRED", "Google token exchange failed. Please reconnect your account.")
        tokens = token_resp.json()
        access_token: str = tokens.get("access_token", "")
        refresh_token: str = tokens.get("refresh_token", "")
        expires_in: int = int(tokens.get("expires_in", 3600))
        if not access_token:
            raise AppError(502, "YOUTUBE_AUTH_EXPIRED", "Google returned no access token.")

        headers = {"Authorization": f"Bearer {access_token}"}
        userinfo_resp = await client.get(_USERINFO_URL, headers=headers)
        google_email = ""
        if userinfo_resp.status_code == 200:
            google_email = userinfo_resp.json().get("email", "")

        channels_resp = await client.get(
            _CHANNELS_URL, params={"part": "snippet,statistics", "mine": "true"}, headers=headers
        )
        if channels_resp.status_code != 200:
            logger.error("YouTube channels fetch failed: %s", channels_resp.text[:300])
            raise AppError(
                502, "YOUTUBE_API_ERROR", "Failed to fetch the YouTube channel from Google."
            )
        items = channels_resp.json().get("items", [])
        if not items:
            raise AppError(404, "YOUTUBE_CHANNEL_NOT_FOUND", "No YouTube channel found for this account.")

        # An account can manage MULTIPLE channels - connect them ALL (the OAuth
        # token works for every channel under this Google account).
        created = 0
        first_channel_id = ""
        first_title = ""
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        for item in items:
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            channel_id = item["id"]

            account = db.query(YouTubeAccount).filter_by(channel_id=channel_id).first()
            if account is None:
                account = YouTubeAccount(
                    user_id=user_id,
                    google_account_email=google_email,
                    channel_id=channel_id,
                    channel_title=snippet.get("title", ""),
                    channel_description=snippet.get("description", ""),
                    channel_thumbnail=snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
                )
                db.add(account)
            else:
                account.user_id = user_id
                account.google_account_email = google_email
                account.channel_title = snippet.get("title", account.channel_title)
                account.channel_description = snippet.get("description", account.channel_description)
                account.channel_thumbnail = (
                    snippet.get("thumbnails", {}).get("default", {}).get("url", "") or account.channel_thumbnail
                )
            account.access_token_encrypted = encrypt_str(access_token)
            if refresh_token:
                account.refresh_token_encrypted = encrypt_str(refresh_token)
            account.token_expiry = expiry
            db.commit()
            db.refresh(account)

            channel = db.query(Channel).filter_by(channel_id=channel_id).first()
            if channel is None:
                channel = Channel(
                    youtube_account_id=account.id,
                    channel_id=channel_id,
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    subscriber_count=int(stats.get("subscriberCount", 0) or 0),
                    view_count=int(stats.get("viewCount", 0) or 0),
                    video_count=int(stats.get("videoCount", 0) or 0),
                )
                db.add(channel)
                db.commit()
            else:
                channel.subscriber_count = int(stats.get("subscriberCount", 0) or 0)
                channel.view_count = int(stats.get("viewCount", 0) or 0)
                channel.video_count = int(stats.get("videoCount", 0) or 0)
                channel.title = snippet.get("title", channel.title)
                db.commit()
            created += 1
            if not first_channel_id:
                # audit_logs.channel_id is an FK to channels.id (internal UUID),
                # NOT the YouTube channel id - using the wrong id breaks the insert.
                first_channel_id = channel.id
                first_title = snippet.get("title", "")

    log_audit(
        db,
        user_id=user_id,
        channel_id=first_channel_id,
        action="youtube_connected",
        target=first_title,
        result="ok",
        metadata={"channels_connected": created, "google_email": google_email},
    )
