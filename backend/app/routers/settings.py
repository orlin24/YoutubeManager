"""Settings: AI model, score weights, notification prefs (persisted JSON)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.decision_engine import DEFAULT_WEIGHTS
from app.auth.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.security import check_csrf

router = APIRouter(prefix="/settings", tags=["settings"])

_DEFAULTS: dict = {
    "ai": {"model": "gpt-4o-mini", "enabled": False},
    "notifications": {"telegram_enabled": False},
    "score_weights": DEFAULT_WEIGHTS,
    "ranges_supported": ["7d", "28d", "90d", "365d", "custom"],
}


def _load(db: Session) -> dict:
    s = get_settings()
    data = dict(_DEFAULTS)
    data["ai"] = {"model": s.AI_MODEL, "enabled": s.ai_enabled}
    row = db.query(AppSetting).filter_by(key="settings").first()
    if row and isinstance(row.value, dict):
        saved = row.value
        if "score_weights" in saved:
            data["score_weights"].update(saved["score_weights"])
        if saved.get("ai") and not s.AI_API_KEY:
            data["ai"]["model"] = saved["ai"].get("model", data["ai"]["model"])
    return data


class AiPatch(BaseModel):
    model: str | None = None


class ScoreWeightsPatch(BaseModel):
    ctr: float | None = None
    retention: float | None = None
    views_velocity: float | None = None
    subscriber_conversion: float | None = None
    watch_time: float | None = None
    engagement: float | None = None


class SettingsUpdate(BaseModel):
    ai: AiPatch | None = None
    score_weights: ScoreWeightsPatch | None = None


class GoogleCredentials(BaseModel):
    client_id: str = Field(min_length=10, max_length=500)
    client_secret: str = Field(min_length=10, max_length=500)


class AiCredentials(BaseModel):
    api_key: str = Field(min_length=5, max_length=500)
    model: str | None = None
    base_url: str | None = None


class TelegramCredentials(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


@router.get("/credentials/status")
def credentials_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    from app.services.config_store import status as config_status

    return config_status(db)


@router.patch("/credentials/google")
def save_google_credentials(payload: GoogleCredentials, request: Request,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    from app.services.config_store import save_google_oauth

    save_google_oauth(db, payload.client_id, payload.client_secret)
    log_audit(db, user_id=user.id, action="google_credentials_updated", target="settings",
              result="ok", metadata={"source": "web"})
    return {"success": True, "configured": True, "message": "Kredensial Google disimpan dan diterapkan."}


@router.patch("/credentials/ai")
def save_ai_credentials(payload: AiCredentials, request: Request,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    from app.services.config_store import save_ai_provider

    save_ai_provider(db, api_key=payload.api_key, model=payload.model, base_url=payload.base_url)
    log_audit(db, user_id=user.id, action="ai_credentials_updated", target="settings",
              result="ok", metadata={"source": "web"})
    return {"success": True, "configured": True, "message": "Kredensial AI disimpan dan diterapkan."}


@router.patch("/credentials/telegram")
def save_telegram_credentials(payload: TelegramCredentials, request: Request,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    from app.services.config_store import save_telegram

    if not payload.bot_token.strip() and not payload.chat_id.strip():
        raise AppError(400, "VALIDATION_ERROR", "Bot token dan Chat ID harus diisi.")
    save_telegram(db, payload.bot_token, payload.chat_id)
    log_audit(db, user_id=user.id, action="telegram_credentials_updated", target="settings",
              result="ok", metadata={"source": "web"})
    return {"success": True, "configured": True, "message": "Kredensial Telegram disimpan dan diterapkan."}


@router.post("/telegram/test")
def test_telegram(request: Request, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    from app.services.telegram_service import send_telegram

    ok = send_telegram("Notifikasi Telegram aktif - AI YouTube Manager siap melapor.")
    if not ok:
        raise AppError(502, "TELEGRAM_FAILED",
                       "Pesan gagal dikirim. Periksa Bot Token, Chat ID, dan pastikan bot sudah ditambahkan ke chat.")
    log_audit(db, user_id=user.id, action="telegram_test", target="settings", result="ok")
    return {"success": True, "message": "Pesan tes terkirim ke Telegram."}


@router.get("")
def get_settings_endpoint(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _load(db)


@router.patch("")
def update_settings(payload: SettingsUpdate, request: Request,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    current = _load(db)
    if payload.score_weights:
        weights = dict(current["score_weights"])
        for k, v in payload.score_weights.model_dump(exclude_none=True).items():
            if k in weights:
                weights[k] = round(max(0.0, min(1.0, float(v))), 3)
        current["score_weights"] = weights
    if payload.ai and payload.ai.model:
        current["ai"]["model"] = payload.ai.model

    row = db.query(AppSetting).filter_by(key="settings").first()
    if row is None:
        row = AppSetting(key="settings", value=current)
        db.add(row)
    else:
        row.value = current
    db.commit()
    log_audit(db, user_id=user.id, action="settings_updated", target="settings", result="ok",
              metadata={"fields": list(payload.model_dump(exclude_none=True).keys())})
    return _load(db)
