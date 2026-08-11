"""GET /api/health - system status for the UI chips and probes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.utils.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger("health")


@router.get("")
def health(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()

    database = "error"
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("DB health check failed", exc_info=exc)

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "checks": {
            "backend": "ok",
            "database": database,
            "youtube_api": "configured" if settings.GOOGLE_CLIENT_ID else "not_configured",
            "ai_provider": "configured" if settings.ai_enabled else "not_configured",
            "redis": "not_configured",  # optional; not wired in the MVP
        },
    }
