"""Notification service abstraction (Telegram/Email/Discord/Webhook ready).

MVP: notifications are optional; nothing is sent unless a provider is configured
via environment variables. The architecture is in place so Telegram/Email/Discord
can be enabled without touching callers.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

import httpx

from app.utils.logging import get_logger

logger = get_logger("notifications")


def alert(**kwargs) -> dict:
    """Build a canonical alert payload:
    channel_title, video_title, metric, message, action_url."""
    return {
        "channel_title": kwargs.get("channel_title", ""),
        "video_title": kwargs.get("video_title", ""),
        "metric": kwargs.get("metric", ""),
        "message": kwargs.get("message", ""),
        "action_url": kwargs.get("action_url", ""),
    }


class NotificationProvider(ABC):
    @abstractmethod
    def send(self, alert: dict) -> bool: ...


class TelegramNotificationProvider(NotificationProvider):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, alert: dict) -> bool:
        try:
            text = (
                f"\u26a0\ufe0f YouTube Alert\n\n"
                f"Channel: {alert.get('channel_title', '-')}\n"
                f"Video: {alert.get('video_title', '-')}\n"
                f"Metric: {alert.get('metric', '-')}\n\n"
                f"{alert.get('message', '')}\n"
                f"{alert.get('action_url', '')}"
            )
            httpx.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=15,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram send failed", exc_info=exc)
            return False


class EmailNotificationProvider(NotificationProvider):
    def send(self, alert: dict) -> bool:
        # SMTP integration point; not wired up in the MVP.
        logger.info("Email notification provider not configured; alert skipped")
        return False


class DiscordNotificationProvider(NotificationProvider):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, alert: dict) -> bool:
        try:
            httpx.post(self.webhook_url, json={"content": alert.get("message", "")}, timeout=15)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Discord send failed", exc_info=exc)
            return False


class WebhookNotificationProvider(NotificationProvider):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, alert: dict) -> bool:
        try:
            httpx.post(self.webhook_url, json=alert, timeout=15)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Webhook send failed", exc_info=exc)
            return False


class NotificationService:
    def __init__(self) -> None:
        self._providers: list[NotificationProvider] = []
        self._load_providers()

    def _load_providers(self) -> None:
        if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
            self._providers.append(
                TelegramNotificationProvider(
                    os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
                )
            )
        if os.getenv("DISCORD_WEBHOOK_URL"):
            self._providers.append(DiscordNotificationProvider(os.getenv("DISCORD_WEBHOOK_URL", "")))
        if os.getenv("NOTIFICATION_WEBHOOK_URL"):
            self._providers.append(WebhookNotificationProvider(os.getenv("NOTIFICATION_WEBHOOK_URL", "")))

    @property
    def configured(self) -> bool:
        return bool(self._providers)

    def send(self, alert: dict) -> bool:
        if not self._providers:
            return False
        ok = True
        for provider in self._providers:
            ok = provider.send(alert) and ok
        return ok


_notification_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
