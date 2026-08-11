"""Videos: list, detail, update (with approval for publishing), upload, delete, analyze."""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.decision_engine import compute_video_score
from app.auth.deps import get_current_user
from app.database import get_db
from app.models.video import Video
from app.models.user import User
from app.routers.deps import get_user_account, get_user_channel, user_channel_ids
from app.services.audit_service import log_audit
from app.services.youtube_service import (
    delete_video_flow,
    sync_video_analytics,
    update_video_metadata,
    YouTubeService,
)
from app.youtube.client import get_authenticated_client
from app.utils.errors import AppError
from app.utils.logging import get_logger
from app.utils.security import check_csrf

router = APIRouter(prefix="/videos", tags=["videos"])
logger = get_logger("videos")


def _video_dict(v: Video) -> dict:
    return {
        "id": v.id,
        "youtube_video_id": v.youtube_video_id,
        "title": v.title,
        "description": v.description,
        "thumbnail_url": v.thumbnail_url,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "duration_seconds": v.duration_seconds,
        "view_count": v.view_count,
        "like_count": v.like_count,
        "comment_count": v.comment_count,
        "privacy_status": v.privacy_status,
        "ctr": v.ctr,
        "average_view_duration_seconds": v.average_view_duration_seconds,
        "ai_score": v.ai_score,
        "channel_id": v.channel_id,
    }


def _get_owned_video(db: Session, user: User, video_id: str) -> Video:
    ids = user_channel_ids(db, user)
    video = db.get(Video, video_id)
    if video is None or video.channel_id not in ids:
        raise AppError(404, "NOT_FOUND", "Video not found.")
    return video


@router.get("")
def list_videos(channel_id: str | None = None, search: str = "", status: str = "",
                sort: str = "latest", limit: int = 50, offset: int = 0,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    q = db.query(Video).filter(Video.channel_id.in_(ids)) if ids else db.query(Video).filter(False)
    if channel_id:
        q = q.filter(Video.channel_id == channel_id)
    if search:
        q = q.filter(Video.title.ilike(f"%{search}%"))
    if status:
        q = q.filter(Video.privacy_status == status)
    if sort == "views":
        q = q.order_by(Video.view_count.desc())
    elif sort == "ai_score":
        q = q.order_by(Video.ai_score.desc().nullslast())
    else:
        q = q.order_by(Video.published_at.desc().nullslast())
    total = q.count()
    videos = q.offset(offset).limit(min(limit, 100)).all()
    return {"items": [_video_dict(v) for v in videos], "total": total}


@router.get("/{video_id}")
def get_video(video_id: str, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)) -> dict:
    return _video_dict(_get_owned_video(db, user, video_id))


class VideoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    privacy_status: str | None = None
    tags: list[str] | None = None


@router.patch("/{video_id}")
def update_video(video_id: str, payload: VideoUpdate, request: Request,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    video = _get_owned_video(db, user, video_id)
    account = get_user_account(db, user, video.channel_id)

    # Visibility/metadata changes apply directly (no approval flow).
    fields = payload.model_dump(exclude_none=True)
    if fields:
        video = update_video_metadata(db, account, video, **fields)
    return _video_dict(video)


# --- Background upload with progress ---------------------------------------
import threading
import uuid
from typing import Callable as _Callable

_UPLOADS: dict[str, dict] = {}
_UPLOADS_LOCK = threading.Lock()


def _upload_set(upload_id: str, **fields) -> None:
    with _UPLOADS_LOCK:
        _UPLOADS.setdefault(upload_id, {})
        _UPLOADS[upload_id].update(fields)


def _upload_snapshot(upload_id: str) -> dict:
    with _UPLOADS_LOCK:
        return dict(_UPLOADS.get(upload_id, {}))


def _try_unlink(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def _run_upload(upload_id: str, tmp_path: str, resume_uri: str | None = None) -> None:
    """Upload the temp file to YouTube with Google's resumable protocol. All
    metadata lives in the _UPLOADS snapshot; resume_uri continues an
    interrupted session (kept when the upload is paused)."""
    from datetime import datetime

    from app.database import SessionLocal
    from app.models.youtube_account import YouTubeAccount
    from app.utils.logging import get_logger as _get_logger

    logger = _get_logger("upload")
    snap = _upload_snapshot(upload_id)
    account_id = snap.get("account_id")
    channel_id = snap.get("channel_id")
    title = snap.get("title", "")
    description = snap.get("description", "")
    target_status = snap.get("target_status", "private")
    tag_list = snap.get("tag_list") or []
    synthetic = snap.get("synthetic", True)
    thumb_data = snap.get("thumb_data")
    thumb_mime = snap.get("thumb_mime")
    plan_item_id = snap.get("plan_item_id")
    user_id = snap.get("user_id")
    publish_dt = None
    if snap.get("publish_at"):
        try:
            publish_dt = datetime.fromisoformat(snap["publish_at"].replace("Z", "+00:00"))
        except ValueError:
            publish_dt = None

    db = SessionLocal()
    done_ok = False
    try:
        _upload_set(upload_id, status="preparing", progress=0, message="Menyiapkan upload...")
        account = db.get(YouTubeAccount, account_id)
        if account is None:
            raise AppError(404, "NOT_FOUND", "Akun YouTube tidak ditemukan.")
        client = get_authenticated_client(db, account)
        service = YouTubeService()

        def _cb(frac: float) -> None:
            _upload_set(upload_id, status="uploading",
                        progress=round(10 + frac * 85, 1),
                        message="Mengunggah ke YouTube...")

        def _session(uri: str) -> None:
            _upload_set(upload_id, resume_uri=uri)

        _upload_set(upload_id, status="uploading", progress=10, message="Mengunggah ke YouTube...")
        video_data = service.upload_video(
            client,
            file_path=tmp_path,
            title=title,
            description=description,
            privacy_status=target_status,
            tags=tag_list or None,
            mimetype="video/mp4",
            contains_synthetic_media=synthetic,
            publish_at=publish_dt,
            progress_cb=_cb,
            session_cb=_session,
            resume_uri=resume_uri,
        )

        _upload_set(upload_id, status="finalizing", progress=95, message="Menyimpan data video...")
        video = Video(
            channel_id=channel_id,
            youtube_video_id=video_data["youtube_video_id"],
            # The insert response may not include the title yet - fall back to the form value.
            title=video_data.get("title") or title,
            description=video_data.get("description") or description,
            thumbnail_url=video_data.get("thumbnail_url", ""),
            privacy_status=video_data.get("privacy_status", target_status),
            published_at=None,
        )
        db.add(video)
        db.commit()
        db.refresh(video)

        # Optional thumbnail (failure never fails the upload).
        thumb_warning: str | None = None
        if thumb_data:
            try:
                from app.services.youtube_service import update_video_thumbnail

                video = update_video_thumbnail(db, account, video, thumb_data,
                                               thumb_mime or "image/jpeg")
            except AppError as exc:
                thumb_warning = f"Video terupload, tapi thumbnail gagal: {exc.message}"
                logger.error("Thumbnail upload AppError for %s: %s",
                             video.youtube_video_id, exc.message)
            except Exception as exc:  # noqa: BLE001
                thumb_warning = "Video terupload, tapi thumbnail gagal (coba lagi dari Edit video)."
                logger.error("Thumbnail upload failed for %s: %s",
                             video.youtube_video_id, exc, exc_info=True)

        log_audit(db, user_id=user_id, channel_id=channel_id, action="video_uploaded",
                  target=video.title, result="ok",
                  metadata={"privacy_status": video.privacy_status, "tags_count": len(tag_list)})

        if plan_item_id:
            from app.models.content_plan_item import ContentPlanItem
            from datetime import date

            item = db.get(ContentPlanItem, plan_item_id)
            if item is not None and item.channel_id == channel_id:
                item.status = "PUBLISHED"
                item.publish_date = date.today()
                item.notes = (item.notes or "") + f"\nVideo: https://youtu.be/{video.youtube_video_id}"
                db.commit()

        result: dict = _video_dict(video)
        if thumb_warning:
            result["thumbnail_warning"] = thumb_warning
        if publish_dt is not None:
            result["scheduled_for"] = publish_dt.isoformat()

        _upload_set(upload_id, status="completed", progress=100, message="Selesai", result=result)
        done_ok = True
    except AppError as exc:
        logger.error("Upload failed: %s", exc.message)
        has_session = bool(_upload_snapshot(upload_id).get("resume_uri"))
        if has_session:
            _upload_set(upload_id, status="paused",
                        message="Upload terputus - bisa dilanjutkan dari posisi terakhir.",
                        error_code=exc.code)
        else:
            _upload_set(upload_id, status="failed", message=exc.message, error_code=exc.code)
    except Exception as exc:  # noqa: BLE001
        logger.error("Upload failed", exc_info=exc)
        has_session = bool(_upload_snapshot(upload_id).get("resume_uri"))
        if has_session:
            _upload_set(upload_id, status="paused",
                        message="Upload terputus - bisa dilanjutkan dari posisi terakhir.",
                        error=str(exc)[:300])
        else:
            _upload_set(upload_id, status="failed", message="Upload gagal: terjadi kesalahan.",
                        error=str(exc)[:300])
    finally:
        # keep the temp file when paused so the upload can resume from the last
        # position; delete it when done or permanently failed.
        snap_now = _upload_snapshot(upload_id)
        if done_ok or snap_now.get("status") != "paused":
            _try_unlink(tmp_path)
        db.close()


@router.post("/upload")
async def init_upload(
    request: Request,
    channel_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    privacy_status: str = Form("private"),
    publish_at: str | None = Form(None),
    tags: str = Form(""),
    content_plan_item_id: str = Form(""),
    contains_synthetic_media: str = Form("true"),
    total_bytes: int = Form(0),
    file: UploadFile = File(...),
    thumbnail: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Start a resumable upload session: save metadata + write the first chunk."""
    check_csrf(request)
    ch = get_user_channel(db, user, channel_id)
    get_user_account(db, user, channel_id)

    import tempfile

    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=os.path.splitext(file.filename or "")[1] or ".mp4"
    )
    received = 0
    try:
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
            received += len(chunk)
        tmp.flush()
    finally:
        tmp.close()
    tmp_path = tmp.name

    publish_dt = None
    if publish_at:
        from datetime import datetime

        try:
            publish_dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
        except ValueError:
            _try_unlink(tmp_path)
            raise AppError(422, "VALIDATION_ERROR", "Format publish_at tidak valid.")

    target_status = "private" if publish_dt is not None else privacy_status
    tag_list = [t.strip() for t in tags.split(",") if t.strip()][:50]
    synthetic = contains_synthetic_media.strip().lower() in ("true", "1", "ya", "yes")

    thumb_data: bytes | None = None
    thumb_mime: str | None = None
    if thumbnail is not None and thumbnail.filename and thumbnail.content_type in _THUMBNAIL_TYPES:
        thumb_data = await thumbnail.read()
        thumb_mime = thumbnail.content_type or "image/jpeg"

    upload_id = str(uuid.uuid4())
    _upload_set(upload_id,
                status="receiving", progress=0, message="Mengunggah ke server...",
                tmp_path=tmp_path, account_id=ch.youtube_account_id, channel_id=ch.id,
                title=title, description=description, target_status=target_status,
                tag_list=tag_list, synthetic=synthetic,
                thumb_data=thumb_data, thumb_mime=thumb_mime,
                plan_item_id=content_plan_item_id or None, user_id=user.id,
                publish_at=(publish_dt.isoformat() if publish_dt else None),
                total_bytes=total_bytes or received, received_bytes=received)
    return {"upload_id": upload_id, "received_bytes": received}


@router.post("/upload-chunk")
async def upload_chunk(
    request: Request,
    upload_id: str = Form(...),
    chunk: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Append the next chunk to the upload session (resume-safe by offset)."""
    check_csrf(request)
    snap = _upload_snapshot(upload_id)
    if not snap:
        raise AppError(404, "NOT_FOUND", "Sesi upload tidak ditemukan.")
    if not snap.get("tmp_path") or not os.path.exists(snap["tmp_path"]):
        raise AppError(410, "UPLOAD_EXPIRED", "Sesi upload tidak ditemukan. Mulai ulang.")
    received = snap.get("received_bytes", 0)
    with open(snap["tmp_path"], "ab") as f:
        while data := await chunk.read(1024 * 1024):
            f.write(data)
            received += len(data)
    total = snap.get("total_bytes", 0) or received
    _upload_set(upload_id, received_bytes=received,
                progress=round(min(received / total, 1.0) * 90, 1) if total else 0)
    return {"upload_id": upload_id, "received_bytes": received, "total_bytes": total}


class _UploadIdPayload(BaseModel):
    upload_id: str


@router.post("/upload-finalize")
async def finalize_upload(payload: _UploadIdPayload, request: Request,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)) -> dict:
    """All bytes received - start the background resumable upload to YouTube."""
    check_csrf(request)
    snap = _upload_snapshot(payload.upload_id)
    if not snap or not snap.get("tmp_path"):
        raise AppError(404, "NOT_FOUND", "Sesi upload tidak ditemukan.")
    if not os.path.exists(snap["tmp_path"]):
        raise AppError(410, "UPLOAD_EXPIRED", "File upload tidak ditemukan. Mulai ulang.")
    received = snap.get("received_bytes", 0)
    total = snap.get("total_bytes", 0)
    if total and received < total:
        raise AppError(409, "UPLOAD_INCOMPLETE",
                       f"Upload belum lengkap ({received}/{total} bytes).")
    _upload_set(payload.upload_id, status="uploading", progress=10, message="Mengunggah ke YouTube...")
    threading.Thread(target=_run_upload, args=(payload.upload_id, snap["tmp_path"]), daemon=True).start()
    return {"upload_id": payload.upload_id, "started": True}


@router.post("/upload-resume")
async def resume_upload(payload: _UploadIdPayload, request: Request,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> dict:
    """Continue a paused upload from its last resumable position (not from 0)."""
    check_csrf(request)
    snap = _upload_snapshot(payload.upload_id)
    if not snap or not snap.get("tmp_path"):
        raise AppError(404, "NOT_FOUND", "Sesi upload tidak ditemukan.")
    if not os.path.exists(snap["tmp_path"]):
        raise AppError(410, "UPLOAD_EXPIRED", "File upload tidak ditemukan. Mulai ulang.")
    resume_uri = snap.get("resume_uri")
    if not resume_uri:
        raise AppError(409, "NOT_RESUMABLE", "Upload ini belum memiliki sesi resumable.")
    _upload_set(payload.upload_id, status="uploading", progress=10,
                message="Melanjutkan upload ke YouTube...")
    threading.Thread(target=_run_upload,
                     args=(payload.upload_id, snap["tmp_path"], resume_uri), daemon=True).start()
    return {"upload_id": payload.upload_id, "resumed": True}


@router.post("/upload-cancel")
async def cancel_upload(payload: _UploadIdPayload, request: Request,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> dict:
    """Discard an upload session (paused or stuck) and free its temp file."""
    check_csrf(request)
    snap = _upload_snapshot(payload.upload_id)
    if snap and snap.get("tmp_path"):
        _try_unlink(snap["tmp_path"])
    _UPLOADS.pop(payload.upload_id, None)
    return {"success": True}


@router.get("/upload-status/{upload_id}")
def upload_status(upload_id: str, user: User = Depends(get_current_user)) -> dict:
    snap = _upload_snapshot(upload_id)
    if not snap:
        raise AppError(404, "NOT_FOUND", "Upload tidak ditemukan.")
    return {k: v for k, v in snap.items() if k not in ("tmp_path", "thumb_data", "tag_list")}


@router.delete("/{video_id}")
def delete_video(video_id: str, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    video = _get_owned_video(db, user, video_id)
    account = get_user_account(db, user, video.channel_id)
    result = delete_video_flow(db, account, video)  # deletes from YouTube + DB directly
    return {"success": True, **result}


_THUMBNAIL_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/{video_id}/thumbnail")
async def upload_thumbnail(
    video_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    check_csrf(request)
    video = _get_owned_video(db, user, video_id)
    if file.content_type not in _THUMBNAIL_TYPES:
        raise AppError(422, "VALIDATION_ERROR",
                       "Thumbnail harus berupa file JPEG, PNG, atau WEBP.")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise AppError(413, "FILE_TOO_LARGE",
                       "Thumbnail terlalu besar (maks 10MB). Gunakan 16:9 (misal 1280x720).")
    # File > 2MB (batas YouTube) otomatis dikompres di set_thumbnail.
    account = get_user_account(db, user, video.channel_id)
    from app.services.youtube_service import update_video_thumbnail

    updated = await asyncio.to_thread(
        update_video_thumbnail, db, account, video, data, file.content_type or "image/jpeg"
    )
    return {"success": True, "video": _video_dict(updated)}


@router.post("/{video_id}/analyze")
async def analyze_video(video_id: str, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> dict:
    video = _get_owned_video(db, user, video_id)
    account = get_user_account(db, user, video.channel_id)
    try:
        await asyncio.to_thread(sync_video_analytics, db, account, video)
        db.refresh(video)
    except AppError as exc:
        logger.warning("Analytics sync skipped for %s: %s", video_id, exc.code)
    score = compute_video_score(video)
    if score.get("score") is not None:
        video.ai_score = score["score"]
        db.commit()
        db.refresh(video)
    log_audit(db, user_id=user.id, channel_id=video.channel_id, action="video_analyzed",
              target=video.title, result="ok", metadata={"score": score.get("score")})
    return {
        "score": score.get("score"),
        "strengths": score.get("strengths", []),
        "weaknesses": score.get("weaknesses", []),
        "explanation": score.get("explanation", ""),
        "ai": score.get("ai", False),
        "video": _video_dict(video),
    }


@router.post("/analyze-all")
def analyze_all_videos(channel_id: str | None = None, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> dict:
    """Compute AI Performance Scores for all videos at once (pure computation)."""
    ids = user_channel_ids(db, user)
    if not ids:
        raise AppError(404, "NOT_FOUND", "Connect a YouTube channel first.")
    channels = [channel_id] if channel_id in ids else ids
    total_scored = total_with = total_without = 0
    for cid in channels:
        from app.services.youtube_service import refresh_channel_scores

        result = refresh_channel_scores(db, cid)
        total_scored += result["scored"]
        total_with += result["with_score"]
        total_without += result["without"]
    log_audit(db, user_id=user.id, action="videos_analyzed_all", target="videos",
              result="ok", metadata={"scored": total_scored, "with_score": total_with})
    return {"scored": total_scored, "with_score": total_with, "without": total_without}
