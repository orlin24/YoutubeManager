"""Backup & restore endpoints: download all data as one file, or restore from one."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import backup_service
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.logging import get_logger
from app.utils.security import check_csrf

router = APIRouter(prefix="/backup", tags=["backup"])
logger = get_logger("backup")


class ExportRequest(BaseModel):
    password: str = ""


@router.post("/export")
async def export_backup(
    request: Request,
    payload: ExportRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download the whole database (channels, videos, OAuth tokens, settings) as one file."""
    check_csrf(request)
    password = (payload.password if payload else "") or None
    body = backup_service.export_backup(db, password)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if password:
        media_type = "application/octet-stream"
        filename = f"ai-youtube-manager-backup-{stamp}.json.enc"
    else:
        media_type = "application/json"
        filename = f"ai-youtube-manager-backup-{stamp}.json"
    try:
        log_audit(db, user_id=user.id, action="backup.export", result="success")
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit log after export failed: %s", exc)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_backup(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace all data on this server with the uploaded backup file."""
    check_csrf(request)
    raw = await file.read()
    if len(raw) > backup_service.MAX_BACKUP_BYTES:
        raise AppError(413, "PAYLOAD_TOO_LARGE", "File backup terlalu besar (maks 100 MB).")
    result = backup_service.import_backup(db, raw, password or None)
    audit_user_id = user.id if user.id in result["user_ids"] else None
    try:
        log_audit(
            db,
            user_id=audit_user_id,
            action="backup.restore",
            result="success",
            metadata={"counts": result["counts"]},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit log after restore failed: %s", exc)
    return {
        "success": True,
        "restored": result["counts"],
        "note": "Semua data diganti dengan isi backup. Token login YouTube dipulihkan - "
        "tidak perlu login ulang. Jika kredensial Google ikut terimpor, restart server "
        "agar diterapkan.",
    }
