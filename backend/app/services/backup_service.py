"""Full-database backup / restore as a single JSON file.

Exports every table (users, YouTube accounts incl. OAuth tokens, channels, videos,
analytics snapshots, content plans, AI memory, approval & audit records, settings)
into one file. On restore the server's data is replaced by the file's contents.

OAuth tokens are written to the file in PLAINTEXT (so the file must be treated as
secret; optionally protect it with a password, which Fernet-encrypts the whole
file) and re-encrypted with the *current* server's key on restore. That means a
restored channel keeps working without re-login, as long as the Google OAuth
client credentials are the same (copy backend/.env, or the credentials were saved
via the web UI - those live in the app_settings table and travel with the backup).
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Date as SQLDate
from sqlalchemy import DateTime, delete
from sqlalchemy.orm import Session

from app.models.ai_decision import AiDecision
from app.models.ai_task import AiTask
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.app_setting import AppSetting
from app.models.approval_request import ApprovalRequest
from app.models.audit_log import AuditLog
from app.models.channel import Channel
from app.models.channel_profile import ChannelProfile
from app.models.content_plan_item import ContentPlanItem
from app.models.content_factory import (
    ContentBrief, ContentExperiment, ContentGenerationLog, ContentIdea,
    ContentPerformance, ContentQueue,
)
from app.models.bi import ForecastHistory
from app.models.learning import LearningMemory, RecommendationOutcome
from app.models.lifecycle import AiPattern, ChannelLifecycle
from app.models.replied_comment import RepliedComment
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services.encryption import decrypt_str, encrypt_str
from app.utils.errors import AppError

APP_MARKER = "ai-youtube-manager"
FORMAT_VERSION = 1
MAX_BACKUP_BYTES = 100 * 1024 * 1024  # 100 MB

# Insert/export order (parents before children). Wipe uses the reverse order so
# foreign keys never block the deletes on PostgreSQL.
TABLE_ORDER: list[tuple[str, Any]] = [
    ("users", User),
    ("app_settings", AppSetting),
    ("youtube_accounts", YouTubeAccount),
    ("channels", Channel),
    ("channel_lifecycle", ChannelLifecycle),
    ("ai_patterns", AiPattern),
    ("content_ideas", ContentIdea),
    ("content_briefs", ContentBrief),
    ("content_queue", ContentQueue),
    ("content_experiments", ContentExperiment),
    ("content_performance", ContentPerformance),
    ("content_generation_logs", ContentGenerationLog),
    ("forecast_history", ForecastHistory),
    ("learning_memories", LearningMemory),
    ("recommendation_outcomes", RecommendationOutcome),
    ("replied_comments", RepliedComment),
    ("channel_profiles", ChannelProfile),
    ("videos", Video),
    ("analytics_snapshots", AnalyticsSnapshot),
    ("content_plan_items", ContentPlanItem),
    ("ai_tasks", AiTask),
    ("ai_decisions", AiDecision),
    ("approval_requests", ApprovalRequest),
    ("audit_logs", AuditLog),
]

_TOKEN_COLUMNS = ("access_token_encrypted", "refresh_token_encrypted")


def _password_key(password: str) -> bytes:
    """Deterministic Fernet key derived from the backup password."""
    return base64.urlsafe_b64encode(hashlib.sha256(password.encode("utf-8")).digest())


# ---- serialization ---------------------------------------------------------


def _to_plain(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _from_plain(value: Any, col) -> Any:
    if value is None:
        return None
    if isinstance(col.type, DateTime):
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None and getattr(col.type, "timezone", False):
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        return value
    if isinstance(col.type, SQLDate):
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value
    return value


# ---- export ----------------------------------------------------------------


def _column_map(model: Any) -> list[tuple[str, str]]:
    """[(column_name, attribute_name)] for every mapped column.

    Attribute name differs from column name for e.g. audit_logs."metadata"
    whose ORM attribute is `details`.
    """
    return [(attr.columns[0].name, attr.key) for attr in model.__mapper__.column_attrs]


def _export_rows(db: Session, model: Any) -> list[dict]:
    rows: list[dict] = []
    for row in db.query(model).all():
        data: dict = {}
        for col_name, attr_name in _column_map(model):
            value = getattr(row, attr_name)
            if model is YouTubeAccount and col_name in _TOKEN_COLUMNS and value:
                try:
                    value = decrypt_str(value)
                except Exception:  # noqa: BLE001 - keep as-is if not decryptable
                    pass
            data[col_name] = _to_plain(value)
        rows.append(data)
    return rows


def export_backup(db: Session, password: str | None = None) -> bytes:
    """Serialize the whole database into a single JSON (optionally encrypted)."""
    payload: dict = {
        "app": APP_MARKER,
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "password_protected": bool(password),
        "tables": {name: _export_rows(db, model) for name, model in TABLE_ORDER},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if password:
        body = Fernet(_password_key(password)).encrypt(body)
    return body


# ---- restore ---------------------------------------------------------------


def _restore_row(model: Any, data: dict) -> dict:
    row: dict = {}
    for col in model.__table__.columns:
        name = col.name
        value = data.get(name)
        if model is YouTubeAccount and name in _TOKEN_COLUMNS and value:
            try:
                value = encrypt_str(value)  # plaintext in file -> encrypted here
            except Exception:  # noqa: BLE001
                pass
        row[name] = _from_plain(value, col)
    return row


def import_backup(db: Session, raw: bytes, password: str | None = None) -> dict:
    """Replace all data with the backup file's contents. Returns per-table counts."""
    data_bytes = raw
    if raw.lstrip()[:1] != b"{":
        if not password:
            raise AppError(
                400,
                "BACKUP_PASSWORD_REQUIRED",
                "File backup ini dilindungi password. Masukkan password-nya.",
            )
        try:
            data_bytes = Fernet(_password_key(password)).decrypt(raw)
        except InvalidToken:
            raise AppError(400, "BAD_BACKUP_PASSWORD", "Password salah untuk file backup ini.")

    try:
        payload = json.loads(data_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise AppError(400, "INVALID_BACKUP", "File bukan backup yang valid.")

    if payload.get("app") != APP_MARKER or payload.get("format_version") != FORMAT_VERSION:
        raise AppError(400, "INVALID_BACKUP", "Versi file backup tidak didukung.")

    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise AppError(400, "INVALID_BACKUP", "File backup tidak memiliki data tabel.")

    counts: dict[str, int] = {}
    user_ids: list[str] = []
    try:
        for name, _model in reversed(TABLE_ORDER):
            db.execute(delete(_model.__table__))
        for name, model in TABLE_ORDER:
            rows = tables.get(name)
            if not isinstance(rows, list):
                raise AppError(400, "INVALID_BACKUP", f"Payload tabel rusak: {name}")
            restored = [_restore_row(model, r) for r in rows]
            if restored:
                db.execute(model.__table__.insert(), restored)
            counts[name] = len(restored)
            if name == "users":
                user_ids = [r.get("id") for r in restored if r.get("id")]
        db.commit()
    except AppError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise AppError(500, "RESTORE_FAILED", f"Restore gagal: {exc}")

    return {"counts": counts, "user_ids": user_ids}
