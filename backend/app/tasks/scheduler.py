"""Background scheduler: periodic channel/video analytics sync + daily report.

Runs in-process via asyncio (no Redis required for the MVP). Jobs are
idempotent and guarded per-account so overlapping runs cannot happen.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from app.config import get_settings
from app.database import SessionLocal
from app.models.ai_task import AiTask
from app.models.youtube_account import YouTubeAccount
from app.services.youtube_service import sync_channel_data, sync_video_analytics
from app.utils.logging import get_logger

logger = get_logger("scheduler")

_RUNNING: set[str] = set()
_task: asyncio.Task | None = None

_HOUR = 3600.0
_CHANNEL_INTERVAL = _HOUR
_VIDEO_INTERVAL = _HOUR * 6
_REPORT_INTERVAL = _HOUR * 24
_REPORT_RUN_INTERVAL = _HOUR  # how often we look for queued daily reports to execute
_TOKEN_INTERVAL = _HOUR / 2  # keep OAuth access tokens fresh (30 min)
_REMINDER_INTERVAL = _HOUR * 6  # Telegram upload reminders (every 6h, daytime only)
_LIFECYCLE_INTERVAL = _HOUR * 24  # channel lifecycle detection (daily)


async def _run_channel_sync() -> None:
    db = SessionLocal()
    try:
        accounts = db.query(YouTubeAccount).all()
        for account in accounts:
            if account.id in _RUNNING:
                continue
            _RUNNING.add(account.id)
            try:
                await asyncio.to_thread(sync_channel_data, db, account, full=True)
                logger.info("Channel sync done: %s", account.channel_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Channel sync failed for %s: %s", account.channel_id, exc)
            finally:
                _RUNNING.discard(account.id)
    finally:
        db.close()


async def _run_video_sync() -> None:
    db = SessionLocal()
    try:
        accounts = db.query(YouTubeAccount).all()
        for account in accounts:
            if account.id in _RUNNING:
                continue
            _RUNNING.add(account.id)
            try:
                await asyncio.to_thread(sync_video_analytics, db, account, None)
                logger.info("Video analytics sync done: %s", account.channel_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Video analytics sync failed for %s: %s", account.channel_id, exc)
            finally:
                _RUNNING.discard(account.id)
    finally:
        db.close()


def _detect_lifecycles() -> None:
    """Detect each channel's lifecycle mode + winners/risks/priorities (pure code)."""
    from app.models.channel import Channel
    from app.services.lifecycle_service import run_channel_analysis

    db = SessionLocal()
    try:
        for channel in db.query(Channel).all():
            try:
                run_channel_analysis(db, channel)
            except Exception as exc:  # noqa: BLE001
                logger.error("Lifecycle detection failed for %s: %s", channel.channel_id, exc)
        logger.info("Lifecycle detection done")
    finally:
        db.close()




async def _run_autonomous_cycle() -> None:
    """Run the autonomous AI employee cycle (interval from settings, dynamic)."""
    from app.services import autonomous_service
    from app.services.audit_service import log_audit

    db = SessionLocal()
    try:
        settings = autonomous_service.get_autonomous_settings(db)
        result = await asyncio.to_thread(autonomous_service.run_cycle, db)
        log_audit(db, user_id=None, action="ai_auto_cycle", result="ok",
                  metadata={"status": result.get("status"),
                            "tasks_created": result.get("tasks_created"),
                            "tasks_executed": result.get("tasks_executed")})
        if result.get("status") not in ("disabled", "off", "emergency_stopped"):
            logger.info("AI autonomous cycle: %s (mode %s, dry_run %s)",
                        result.get("status"), settings.get("mode"), settings.get("dry_run"))
    except Exception as exc:  # noqa: BLE001
        logger.error("Autonomous cycle failed", exc_info=exc)
    finally:
        db.close()


def _content_factory_daily() -> None:
    """Daily: auto content planning (queue low -> ideas) + AI CEO report."""
    from app.models.channel import Channel
    from app.models.content_factory import ContentQueue
    from app.services import ceo_service, content_factory

    db = SessionLocal()
    try:
        channels = db.query(Channel).all()
        channel_ids = [c.id for c in channels]
        total_queue = (
            db.query(ContentQueue)
            .filter(ContentQueue.channel_id.in_(channel_ids),
                    ContentQueue.status.in_(("READY", "QUALITY_CHECK", "PRODUCTION", "UPLOAD_QUEUE")))
            .count()
            if channel_ids else 0
        )
        if total_queue < content_factory.QUEUE_LOW_THRESHOLD:
            for channel in channels[:2]:  # bounded cost
                try:
                    content_factory.generate_ideas(db, channel, count=4)
                    logger.info("Auto content ideas for %s", channel.channel_id)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Auto idea generation failed: %s", exc)
        try:
            ceo_service.telegram_ceo_report(db, channel_ids)
        except Exception as exc:  # noqa: BLE001
            logger.error("CEO report failed: %s", exc)
    finally:
        db.close()


def _run_bi_daily() -> None:
    """Daily BI: compute cached snapshot + forecast accuracy + morning report."""
    from app.services import bi_engine

    db = SessionLocal()
    try:
        bi_engine.compute_snapshot(db)
        bi_engine.forecast_accuracy(db)
        bi_engine.morning_report(db)
        # automatic learning (audit #16, #19): expected vs actual + confidence decay
        from app.services import learning_service

        result = learning_service.evaluate_outcomes(db)
        if result.get("evaluated"):
            logger.info("AI learning: %s", result)
        logger.info("BI daily job done")
    except Exception as exc:  # noqa: BLE001
        logger.error("BI daily job failed", exc_info=exc)
    finally:
        db.close()


def _send_daily_brief() -> None:
    """Portfolio-wide daily brief to Telegram (once per day)."""
    from app.services import autonomous_service

    db = SessionLocal()
    try:
        autonomous_service.daily_brief(db)
    finally:
        db.close()



def _autonomous_interval_minutes() -> float:
    """Read AI_CHECK_INTERVAL (minutes) dynamically so changes apply live."""
    try:
        from app.config import get_settings
        from app.models.app_setting import AppSetting

        db = SessionLocal()
        try:
            row = db.query(AppSetting).filter_by(key="autonomous.settings").first()
            if row and isinstance(row.value, dict) and row.value.get("check_interval_minutes"):
                return float(row.value["check_interval_minutes"]) * 60.0
        finally:
            db.close()
        return float(get_settings().AI_CHECK_INTERVAL) * 60.0
    except Exception:
        return _HOUR

def _queue_daily_report() -> None:
    db = SessionLocal()
    try:
        accounts = db.query(YouTubeAccount).all()
        queued_any = False
        for account in accounts:
            channel = account.channel
            if channel is None:
                continue
            already_pending = (
                db.query(AiTask)
                .filter(
                    AiTask.channel_id == channel.id,
                    AiTask.task_type == "daily_report",
                    AiTask.status == "queued",
                )
                .first()
            )
            if already_pending is not None:
                continue  # never pile up duplicate queued reports
            db.add(
                AiTask(
                    channel_id=channel.id,
                    task_type="daily_report",
                    instruction="Produce today's channel report.",
                    status="queued",
                )
            )
            queued_any = True
        db.commit()
        if queued_any:
            logger.info("Queued daily report task(s)")
    finally:
        db.close()


async def _refresh_account_tokens() -> None:
    """Proactively refresh every connected account's access token and mark any
    account whose refresh token is invalid (auth_error) so the UI can show a
    clear 'reconnect' warning instead of failing silently later."""
    from app.youtube.client import _build_credentials
    from app.utils.errors import AppError

    db = SessionLocal()
    try:
        accounts = db.query(YouTubeAccount).all()
        for acc in accounts:
            if acc.id in _RUNNING:
                continue
            try:
                _build_credentials(db, acc)
            except AppError:
                pass  # _build_credentials already stored auth_error on the account
    finally:
        db.close()


def _cadence_label(days: int) -> str:
    if days == 7:
        return "1 minggu"
    return f"{days} hari"


def _should_remind(cadence: int, last_upload_day: date | None,
                   last_reminder_day: date | None, today: date) -> bool:
    """True when the channel is overdue AND we haven't reminded in this window."""
    if not cadence or cadence <= 0 or last_upload_day is None:
        return False
    if (today - last_upload_day).days < cadence:
        return False
    if last_reminder_day is not None and (today - last_reminder_day).days < cadence:
        return False
    return True


def _check_upload_reminders() -> None:
    """Send a Telegram reminder for channels that missed their upload cadence.
    Only runs during daytime (08:00-21:00 server-local) and at most once per
    cadence window per channel."""
    from app.models.channel_profile import ChannelProfile
    from app.models.video import Video
    from app.services.telegram_service import send_telegram

    db = SessionLocal()
    try:
        hour = (datetime.now(timezone.utc) + timedelta(hours=7)).hour  # WIB
        if not (8 <= hour <= 21):
            return
        today = date.today()
        profiles = (
            db.query(ChannelProfile)
            .filter(ChannelProfile.upload_cadence_days.isnot(None))
            .all()
        )
        for profile in profiles:
            cadence = profile.upload_cadence_days or 0
            last = (
                db.query(Video.published_at)
                .filter(Video.channel_id == profile.channel_id)
                .order_by(Video.published_at.desc())
                .first()
            )
            last_day = last[0].date() if (last and last[0] is not None) else None
            last_rem = profile.last_reminder_at.date() if profile.last_reminder_at else None
            if not _should_remind(cadence, last_day, last_rem, today):
                continue
            channel = db.get(Channel, profile.channel_id)
            if channel is None:
                continue
            name = channel.title or channel.channel_id
            text = (
                f"Pengingat upload - {name}\n"
                f"Belum ada video baru sejak {last_day} ({today - last_day.days} hari lalu).\n"
                f"Jadwal: upload setiap {_cadence_label(cadence)}.\n"
                "Saatnya upload konten baru!"
            )
            if send_telegram(text):
                profile.last_reminder_at = datetime.now(timezone.utc)
                db.commit()
                logger.info("Upload reminder sent for %s", channel.channel_id)
    finally:
        db.close()


async def _run_pending_daily_reports() -> None:
    """Execute queued daily_report AI tasks: one real AI run per channel per day.
    Sends the summary to Telegram when configured."""
    from app.ai.service import run_daily_report
    from app.models.user import User
    from app.services.telegram_service import send_telegram

    db = SessionLocal()
    try:
        accounts = db.query(YouTubeAccount).all()
        for account in accounts:
            channel = account.channel
            if channel is None or account.id in _RUNNING:
                continue
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            done_today = (
                db.query(AiTask)
                .filter(
                    AiTask.channel_id == channel.id,
                    AiTask.task_type == "daily_report",
                    AiTask.status == "completed",
                    AiTask.completed_at >= today_start,
                )
                .first()
            )
            queued = (
                db.query(AiTask)
                .filter(
                    AiTask.channel_id == channel.id,
                    AiTask.task_type == "daily_report",
                    AiTask.status == "queued",
                )
                .order_by(AiTask.created_at.asc())
                .first()
            )
            if done_today:
                # supersede any stale queued reports so they stop piling up
                for t in db.query(AiTask).filter(
                    AiTask.channel_id == channel.id,
                    AiTask.task_type == "daily_report",
                    AiTask.status == "queued",
                ).all():
                    t.status = "cancelled"
                    t.error = "superseded by today's report"
                db.commit()
                continue
            if queued is None:
                continue
            _RUNNING.add(account.id)
            try:
                user = db.get(User, account.user_id) if account.user_id else None
                result = await asyncio.to_thread(run_daily_report, db, channel, queued, user)
                summary = (result.get("summary") or "").strip()
                # the report already starts with its own "📊 LAPORAN HARIAN AI — <channel>" header
                text = summary[:3800] if summary else (
                    f"Laporan harian AI - {account.channel_title}: tidak ada data."
                )
                if not send_telegram(text):
                    logger.info("Telegram not configured; daily report stored in app")
            except Exception as exc:  # noqa: BLE001
                logger.error("Daily report failed for %s: %s", account.channel_id, exc)
                if queued.status == "queued":
                    queued.status = "failed"
                    queued.error = str(exc)[:500]
                    db.commit()
            finally:
                _RUNNING.discard(account.id)
    finally:
        db.close()


async def scheduler_loop() -> None:
    last_channel = 0.0
    last_video = 0.0
    last_report = 0.0
    last_report_run = 0.0
    last_token = 0.0
    last_reminder = 0.0
    last_lifecycle = 0.0
    last_autonomous = 0.0
    last_brief = 0.0
    logger.info("Scheduler started")
    while True:
        now = asyncio.get_event_loop().time()
        try:
            if now - last_channel >= _CHANNEL_INTERVAL:
                await _run_channel_sync()
                last_channel = now
            if now - last_video >= _VIDEO_INTERVAL:
                await _run_video_sync()
                last_video = now
            if now - last_report >= _REPORT_INTERVAL:
                _queue_daily_report()
                last_report = now
            if now - last_report_run >= _REPORT_RUN_INTERVAL:
                await _run_pending_daily_reports()
                last_report_run = now
            if now - last_token >= _TOKEN_INTERVAL:
                await _refresh_account_tokens()
                last_token = now
            if now - last_reminder >= _REMINDER_INTERVAL:
                await asyncio.to_thread(_check_upload_reminders)
                last_reminder = now
            if now - last_lifecycle >= _LIFECYCLE_INTERVAL:
                await asyncio.to_thread(_detect_lifecycles)
                await asyncio.to_thread(_send_daily_brief)
                await asyncio.to_thread(_content_factory_daily)
                await asyncio.to_thread(_run_bi_daily)
                last_lifecycle = now
            if now - last_autonomous >= _autonomous_interval_minutes():
                await _run_autonomous_cycle()
                last_autonomous = now
        except Exception as exc:  # noqa: BLE001
            logger.error("Scheduler tick failed", exc_info=exc)
        await asyncio.sleep(60)


def start_scheduler() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.get_running_loop().create_task(scheduler_loop())
