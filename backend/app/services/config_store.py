"""Web-configured credentials (Google OAuth / AI provider) stored in the DB.

Env (.env) remains the baseline; values saved from the web UI (app_settings
table) take precedence and are applied to the live cached Settings at save time
AND at application startup, so changes survive restarts without editing .env.

Secrets are never returned by any API endpoint.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.app_setting import AppSetting
from app.utils.logging import get_logger

logger = get_logger("config_store")

KEY_GOOGLE = "credentials.google_oauth"
KEY_AI = "credentials.ai_provider"
KEY_TELEGRAM = "credentials.telegram"


def _get(db: Session, key: str) -> dict:
    row = db.query(AppSetting).filter_by(key=key).first()
    return row.value if row and isinstance(row.value, dict) else {}


def _set(db: Session, key: str, value: dict) -> None:
    row = db.query(AppSetting).filter_by(key=key).first()
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def save_google_oauth(db: Session, client_id: str, client_secret: str) -> None:
    _set(db, KEY_GOOGLE, {"client_id": client_id.strip(), "client_secret": client_secret.strip()})
    apply_overrides(db)


def save_telegram(db: Session, bot_token: str, chat_id: str) -> None:
    _set(db, KEY_TELEGRAM, {"bot_token": bot_token.strip(), "chat_id": chat_id.strip()})
    apply_overrides(db)


def save_ai_provider(
    db: Session,
    *,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
) -> None:
    value: dict = {"api_key": api_key.strip()}
    if model:
        value["model"] = model.strip()
    if base_url:
        value["base_url"] = base_url.strip()
    _set(db, KEY_AI, value)
    apply_overrides(db)


def apply_overrides(db: Session) -> None:
    """Sync DB-stored credentials into the live (cached) Settings instance."""
    s = get_settings()
    google = _get(db, KEY_GOOGLE)
    if google.get("client_id") and google.get("client_secret"):
        s.GOOGLE_CLIENT_ID = google["client_id"]
        s.GOOGLE_CLIENT_SECRET = google["client_secret"]
        logger.info("Google OAuth credentials applied from web configuration")
    ai = _get(db, KEY_AI)
    if ai.get("api_key"):
        s.AI_API_KEY = ai["api_key"]
        if ai.get("model"):
            s.AI_MODEL = ai["model"]
        if ai.get("base_url"):
            s.AI_BASE_URL = ai["base_url"]
        logger.info("AI provider credentials applied from web configuration")
    telegram = _get(db, KEY_TELEGRAM)
    if telegram.get("bot_token") and telegram.get("chat_id"):
        s.TELEGRAM_BOT_TOKEN = telegram["bot_token"]
        s.TELEGRAM_CHAT_ID = telegram["chat_id"]
        logger.info("Telegram credentials applied from web configuration")


def apply_overrides_on_startup() -> None:
    """Called from the app lifespan so DB credentials survive restarts."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        apply_overrides(db)
    finally:
        db.close()


def status(db: Session) -> dict:
    """Configured/source status. Never includes the secret values."""
    s = get_settings()
    google = _get(db, KEY_GOOGLE)
    ai = _get(db, KEY_AI)

    google_from_web = bool(google.get("client_id") and google.get("client_secret"))
    google_from_env = bool(s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET)
    ai_from_web = bool(ai.get("api_key"))
    ai_from_env = bool(s.AI_API_KEY)

    return {
        "google": {
            "configured": google_from_web or google_from_env,
            "source": "web" if google_from_web else ("env" if google_from_env else "none"),
            "has_client_id": bool(google.get("client_id") or s.GOOGLE_CLIENT_ID),
        },
        "ai": {
            "configured": ai_from_web or ai_from_env,
            "source": "web" if ai_from_web else ("env" if ai_from_env else "none"),
            "has_api_key": bool(ai.get("api_key") or s.AI_API_KEY),
        },
        "telegram": {
            "configured": bool(s.TELEGRAM_BOT_TOKEN and s.TELEGRAM_CHAT_ID),
            "has_bot_token": bool(s.TELEGRAM_BOT_TOKEN),
            "has_chat_id": bool(s.TELEGRAM_CHAT_ID),
        },
        "note": "Secrets are never returned by the API.",
    }
