"""Telegram notifications. Reads bot token + chat id from settings (env or the
web-configured credentials stored in app_settings via config_store). Fails soft:
if Telegram is not configured, send_telegram simply returns False."""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger("telegram")

_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_TEXT = 3800


def is_configured() -> bool:
    s = get_settings()
    return bool(s.TELEGRAM_BOT_TOKEN and s.TELEGRAM_CHAT_ID)


def send_telegram(text: str, bot_token: str | None = None, chat_id: str | None = None) -> bool:
    """Send a text message to Telegram. Returns False when not configured or on failure."""
    token = bot_token or getattr(get_settings(), "TELEGRAM_BOT_TOKEN", "") or ""
    chat = chat_id or getattr(get_settings(), "TELEGRAM_CHAT_ID", "") or ""
    if not token or not chat:
        return False
    try:
        resp = httpx.post(
            _API.format(token=token),
            json={"chat_id": chat, "text": text[:_MAX_TEXT], "disable_web_page_preview": True},
            timeout=15,
        )
        ok = resp.status_code == 200 and resp.json().get("ok")
        if not ok:
            logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text[:200])
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram send error: %s", exc)
        return False
