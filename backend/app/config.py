"""Application settings loaded from environment / backend/.env."""
from __future__ import annotations

import base64
import hashlib
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    APP_NAME: str = "AI YouTube Manager"
    APP_ENV: str = "development"  # development | production
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 5000
    APP_ORIGINS: str = "http://localhost:5173,http://localhost:5000"

    DATABASE_URL: str = "postgresql+psycopg://localhost:5432/ai_youtube_manager"

    SECRET_KEY: str = ""
    TOKEN_ENCRYPTION_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:5000/api/auth/google/callback"

    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"
    AI_BASE_URL: str = "https://api.openai.com/v1"

    REDIS_URL: str = ""
    FRONTEND_URL: str = "http://localhost:5000"
    LOG_LEVEL: str = "INFO"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Autonomous AI employee (off by default; enable via web dashboard / env)
    AI_AUTONOMOUS_ENABLED: bool = False
    AI_CHECK_INTERVAL: int = 60  # minutes between autonomous cycles
    AI_MODE: str = "RECOMMEND_ONLY"  # OFF | RECOMMEND_ONLY | SEMI_AUTO | FULL_AUTO
    AI_DRY_RUN: bool = True  # safety: simulate, never touch YouTube when True
    MAX_ACTIONS_PER_DAY: int = 20
    AI_EMERGENCY_STOP: bool = False

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}

    # ---- derived helpers -------------------------------------------------
    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.APP_ORIGINS.split(",") if o.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.AI_API_KEY)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def effective_secret_key(self) -> str:
        if self.SECRET_KEY:
            return self.SECRET_KEY
        # Dev-only ephemeral key so the app runs before .env is configured.
        return secrets.token_urlsafe(48)

    @property
    def encryption_key(self) -> str:
        """A urlsafe-base64 32-byte Fernet key."""
        if self.TOKEN_ENCRYPTION_KEY:
            return self.TOKEN_ENCRYPTION_KEY
        digest = hashlib.sha256(self.effective_secret_key.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode()


@lru_cache
def get_settings() -> Settings:
    return Settings()
