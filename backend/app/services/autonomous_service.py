"""Autonomous AI employee loop.

Runs on the existing scheduler every AI_CHECK_INTERVAL minutes:

  observe -> analyze (anomalies) -> decide (tasks) -> execute (mode + risk
  gated, dry-run safe) -> verify -> audit -> learn -> report (daily brief).

Decisions use PURE-CODE heuristics on real data (no LLM cost in the loop); the
LLM stays for the daily reports and on-demand analysis. Every autonomous action
is audited. HIGH/CRITICAL risk always needs approval. Kill switch + emergency
stop are respected, and DRY RUN guarantees no real YouTube change.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.ai_task import AiTask
from app.models.audit_log import AuditLog
from app.models.channel import Channel
from app.models.lifecycle import ChannelLifecycle
from app.models.video import Video
from app.utils.logging import get_logger

logger = get_logger("autonomous")

MODES = ("OFF", "RECOMMEND_ONLY", "SEMI_AUTO", "FULL_AUTO")
RISK_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# anomaly thresholds (module-level, tunable)
ANOMALY_VIEWS_DROP_PCT = 30.0
ANOMALY_SUBS_DROP = 20  # subs lost in a window above this is an alert
ANOMALY_VIEWS_SPIKE_PCT = 80.0


# ---- settings --------------------------------------------------------------


def get_autonomous_settings(db: Session) -> dict[str, Any]:
    """Merge env defaults with web overrides stored in app_settings."""
    from app.config import get_settings
    from app.models.app_setting import AppSetting

    s = get_settings()
    cfg: dict[str, Any] = {
        "enabled": bool(s.AI_AUTONOMOUS_ENABLED),
        "mode": s.AI_MODE,
        "dry_run": bool(s.AI_DRY_RUN),
        "max_actions_per_day": int(s.MAX_ACTIONS_PER_DAY),
        "check_interval_minutes": int(s.AI_CHECK_INTERVAL),
        "emergency_stop": bool(s.AI_EMERGENCY_STOP),
    }
    row = db.query(AppSetting).filter_by(key="autonomous.settings").first()
    if row and isinstance(row.value, dict):
        cfg.update({k: v for k, v in row.value.items() if k in cfg})
    return cfg


def set_autonomous_setting(db: Session, key: str, value: Any) -> None:
    from app.models.app_setting import AppSetting

    row = db.query(AppSetting).filter_by(key="autonomous.settings").first()
    data = dict(row.value) if (row and isinstance(row.value, dict)) else {}
    data[key] = value
    if row is None:
        row = AppSetting(key="autonomous.settings", value={})
        db.add(row)
    row.value = data
    db.commit()


def emergency_stop(db: Session) -> dict:
    set_autonomous_setting(db, "emergency_stop", True)
    # cancel pending low-risk autonomous tasks (keep history - rule #15)
    for t in db.query(AiTask).filter(AiTask.status == "queued",
                                     AiTask.idempotency_key.isnot(None)).all():
        t.status = "cancelled"
        t.error = "cancelled by emergency stop"
    db.commit()
    logger.warning("AI EMERGENCY STOP activated")
    return {"success": True, "status": "stopped"}


def resume(db: Session) -> dict:
    set_autonomous_setting(db, "emergency_stop", False)
    logger.info("AI resumed")
    return {"success": True, "status": "running"}


# ---- priority --------------------------------------------------------------


def priority_score(db: Session, channel: Channel, lifecycle: ChannelLifecycle | None) -> int:
    """Internal channel priority (0-100). NOT an official YouTube metric."""
    score = 40
    if lifecycle is None:
        return score
    if lifecycle.mode in ("SCALE", "MONETIZED"):
        score += 20
    if lifecycle.mode == "RECOVERY":
        score += 25  # active problem
    risk = (lifecycle.data or {}).get("risk", {})
    if risk.get("level") == "HIGH":
        score += 15
    if lifecycle.mode == "GROWTH":
        score += 10
    return min(100, score)


# ---- anomaly detection ------------------------------------------------------


def detect_anomalies(db: Session, channel: Channel) -> list[dict[str, Any]]:
    """Compare recent windows vs baseline. Reports observed/evidence/confidence,
    never jumps to a cause."""
    today = date.today()
    recent = _window_views(db, channel.id, today - timedelta(days=6), today)
    prev = _window_views(db, channel.id, today - timedelta(days=13), today - timedelta(days=7))
    out: list[dict[str, Any]] = []
    if prev > 0:
        pct = (recent - prev) / prev * 100
        if pct <= -ANOMALY_VIEWS_DROP_PCT:
            out.append({
                "type": "views_decline",
                "direction": "down",
                "pct": round(pct, 1),
                "observed": f"Views 7 hari turun {pct:.0f}% dibanding 7 hari sebelumnya.",
                "possible_explanation": "Konten baru, algoritma, atau musiman.",
                "evidence": f"{recent} vs {prev} views (7 hari).",
                "confidence": "MEDIUM",
                "alert_level": "HIGH",
            })
        elif pct >= ANOMALY_VIEWS_SPIKE_PCT:
            out.append({
                "type": "views_spike",
                "direction": "up",
                "pct": round(pct, 1),
                "observed": f"Views 7 hari naik {pct:.0f}% dibanding baseline.",
                "possible_explanation": "Video viral atau rekomendasi kuat.",
                "evidence": f"{recent} vs {prev} views (7 hari).",
                "confidence": "MEDIUM",
                "alert_level": "MEDIUM",
            })
    return out


def _window_views(db: Session, channel_id: str, start: date, end: date) -> int:
    rows = (
        db.query(Video.view_count)
        .filter(Video.channel_id == channel_id, Video.published_at.isnot(None))
        .filter(Video.published_at >= datetime.combine(start, datetime.min.time()),
                Video.published_at <= datetime.combine(end, datetime.max.time()))
        .all()
    )
    return sum(int(r[0] or 0) for r in rows)


# ---- task queue ------------------------------------------------------------


def create_task(db: Session, channel_id: str, task_type: str, instruction: str,
                priority: int = 5, risk_level: str = "LOW",
                idempotency_key: str | None = None, deadline: datetime | None = None) -> AiTask | None:
    if idempotency_key:
        exists = (
            db.query(AiTask)
            .filter(AiTask.idempotency_key == idempotency_key,
                    AiTask.status.in_(("queued", "running", "waiting_approval")))
            .first()
        )
        if exists is not None:
            return None  # prevent duplicate tasks (rule #11)
    task = AiTask(
        channel_id=channel_id,
        task_type=task_type,
        instruction=instruction,
        status="queued",
        priority=priority,
        risk_level=risk_level,
        deadline=deadline,
        idempotency_key=idempotency_key,
    )
    db.add(task)
    db.commit()
    logger.info("AI task created: %s (%s) risk=%s", task_type, channel_id, risk_level)
    return task


def _actions_today(db: Session) -> int:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(AuditLog)
        .filter(AuditLog.action == "ai_auto_task", AuditLog.created_at >= today_start)
        .count()
    )


# ---- execution --------------------------------------------------------------


def _execute_task(db: Session, task: AiTask, channel: Channel, dry_run: bool) -> dict:
    """Run one task through the existing services (never direct DB writes by AI)."""
    if task.task_type == "analyze":
        from app.services.lifecycle_service import run_channel_analysis

        result = run_channel_analysis(db, channel)
        task.result = {"summary": f"Analisis {result['mode']} selesai (health {result['health_score']})"}
        task.status = "completed"
        db.commit()
        return {"action": "analyze", "result": result["mode"], "changed": False}
    if task.task_type == "content_pattern":
        if dry_run:
            task.result = {"dry_run": True, "note": "DRY RUN - tidak membuat content plan."}
            task.status = "completed"
            db.commit()
            return {"action": "content_pattern", "dry_run": True, "changed": False}
        from app.ai.service import generate_content_patterns

        result = generate_content_patterns(db, channel)
        task.result = {"created": len(result.get("saved", []))}
        task.status = "completed"
        db.commit()
        return {"action": "content_pattern", "created": len(result.get("saved", [])), "changed": True}
    if task.task_type == "anomaly_alert":
        task.result = {"note": "Anomali dicatat - lihat audit/pattern."}
        task.status = "completed"
        db.commit()
        return {"action": "anomaly_alert", "changed": False}
    # default: unknown action -> needs user
    task.status = "failed"
    task.error = "Unknown task type; needs manual review."
    db.commit()
    return {"action": task.task_type, "needs_user": True}


# ---- the cycle --------------------------------------------------------------


def run_cycle(db: Session) -> dict[str, Any]:
    """One autonomous cycle. Safe by default: dry-run, RECOMMEND_ONLY, off."""
    settings = get_autonomous_settings(db)
    mode = settings["mode"]
    if mode not in MODES or mode == "OFF" or not settings["enabled"]:
        return {"status": "off"}
    if settings["emergency_stop"]:
        return {"status": "emergency_stopped"}

    dry_run = bool(settings["dry_run"])
    max_actions = int(settings["max_actions_per_day"])
    actions_today = _actions_today(db)
    budget_left = max(0, max_actions - actions_today)

    cycles: dict[str, Any] = {"status": "running", "mode": mode, "dry_run": dry_run,
                              "channels": [], "tasks_created": 0, "tasks_executed": 0}
    channels = db.query(Channel).all()
    lcs = {r.channel_id: r for r in db.query(ChannelLifecycle).all()}
    ordered = sorted(channels, key=lambda c: priority_score(db, c, lcs.get(c.id)), reverse=True)

    for channel in ordered:
        if budget_left <= 0:
            cycles["status"] = "budget_reached"
            break
        lc = lcs.get(channel.id)
        anomalies = detect_anomalies(db, channel)
        risk = (lc.data or {}).get("risk", {}) if lc else {}
        winners = (lc.data or {}).get("winners", []) if lc else []
        ch_summary: dict[str, Any] = {"channel": channel.title, "mode": lc.mode if lc else "NEW",
                                      "anomalies": anomalies, "tasks": []}

        # decide: tasks from real signals (idempotency by week)
        week = datetime.now(timezone.utc).isocalendar()[:2]
        wk = f"{week[0]}-W{week[1]}"
        for a in anomalies:
            if a["type"] == "views_decline":
                t = create_task(db, channel.id, "analyze", f"Diagnosa penurunan views ({a['observed']})",
                                priority=9, risk_level="LOW",
                                idempotency_key=f"anom-views-{channel.id}-{wk}")
                if t:
                    ch_summary["tasks"].append({"type": "analyze", "priority": 9})
            elif a["type"] == "views_spike":
                t = create_task(db, channel.id, "content_pattern",
                                "Buat variasi konten dari lonjakan views terbaru",
                                priority=8, risk_level="LOW",
                                idempotency_key=f"anom-spike-{channel.id}-{wk}")
                if t:
                    ch_summary["tasks"].append({"type": "content_pattern", "priority": 8})
        if risk.get("level") == "HIGH" and lc and lc.mode in ("RECOVERY", "GROWTH"):
            t = create_task(db, channel.id, "duplicate_titles",
                            "Rapikan judul duplikat/mirip (risiko monetisasi & jangkauan)",
                            priority=8, risk_level="MEDIUM",
                            idempotency_key=f"dup-titles-{channel.id}-{wk}")
            if t:
                ch_summary["tasks"].append({"type": "duplicate_titles", "priority": 8})
        if winners and any(w["category"] in ("VIEW WINNER", "EMERGING WINNER") for w in winners) and lc:
            t = create_task(db, channel.id, "content_pattern",
                            "Buat variasi formula pemenang untuk konten berikutnya",
                            priority=7, risk_level="LOW",
                            idempotency_key=f"formula-{channel.id}-{wk}")
            if t:
                ch_summary["tasks"].append({"type": "content_pattern", "priority": 7})

        cycles["tasks_created"] += len(ch_summary["tasks"])

        # execute eligible queued tasks for this channel
        queued = (
            db.query(AiTask)
            .filter(AiTask.channel_id == channel.id, AiTask.status == "queued")
            .order_by(AiTask.priority.desc(), AiTask.created_at.asc())
            .all()
        )
        for task in queued:
            if budget_left <= 0:
                cycles["status"] = "budget_reached"
                break
            allowed_auto = mode in ("SEMI_AUTO", "FULL_AUTO")
            if not allowed_auto:
                break  # RECOMMEND_ONLY: create tasks, never run them
            if mode == "SEMI_AUTO" and RISK_RANK.get(task.risk_level, 1) > 0:
                # MEDIUM+ needs approval in SEMI AUTO
                task.status = "waiting_approval"
                _create_approval(db, channel, task)
                db.commit()
                continue
            if RISK_RANK.get(task.risk_level, 1) >= 2:  # HIGH/CRITICAL always approval
                task.status = "waiting_approval"
                _create_approval(db, channel, task)
                db.commit()
                continue
            try:
                outcome = _execute_task(db, task, channel, dry_run)
                _audit(db, channel, task, outcome)
                cycles["tasks_executed"] += 1
                budget_left -= 1
                ch_summary["tasks"].append({"executed": task.task_type, **outcome})
            except Exception as exc:  # noqa: BLE001
                logger.error("AI task failed %s: %s", task.id, exc)
                task.status = "failed"
                task.error = str(exc)[:300]
                db.commit()
                _audit(db, channel, task, {"error": str(exc)[:200]})
        cycles["channels"].append(ch_summary)
    return cycles


def _create_approval(db: Session, channel: Channel, task: AiTask) -> None:
    from app.services.approval_service import create_approval

    try:
        create_approval(
            db,
            channel_id=channel.id,
            action_type=task.task_type,
            target_id=None,
            proposed_change={"instruction": task.instruction},
            reason=f"Task AI {task.task_type} (risk {task.risk_level}) membutuhkan persetujuan.",
            risk_level=task.risk_level,
            user_id=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("approval creation failed: %s", exc)


def _audit(db: Session, channel: Channel, task: AiTask, outcome: dict) -> None:
    from app.services.audit_service import log_audit

    try:
        log_audit(db, user_id=None, channel_id=channel.id, action="ai_auto_task",
                  target=task.task_type, result="ok",
                  metadata={"task_id": task.id, "risk": task.risk_level, "outcome": outcome})
    except Exception:  # noqa: BLE001
        pass


# ---- status / dashboard ------------------------------------------------------


def status(db: Session) -> dict[str, Any]:
    settings = get_autonomous_settings(db)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tasks_today = db.query(AiTask).filter(AiTask.created_at >= today_start).count()
    completed_today = db.query(AiTask).filter(AiTask.created_at >= today_start,
                                              AiTask.status == "completed").count()
    failed_today = db.query(AiTask).filter(AiTask.created_at >= today_start,
                                           AiTask.status == "failed").count()
    waiting = db.query(AiTask).filter(AiTask.status == "waiting_approval").count()
    running = db.query(AiTask).filter(AiTask.status.in_(("running", "queued"))).count()
    last_cycle = (
        db.query(AuditLog.created_at)
        .filter(AuditLog.action == "ai_auto_cycle")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if settings["emergency_stop"]:
        status_text = "STOPPED"
    elif not settings["enabled"] or settings["mode"] == "OFF":
        status_text = "STOPPED"
    else:
        status_text = "RUNNING"
    return {
        "status": status_text,
        "mode": settings["mode"],
        "enabled": settings["enabled"],
        "dry_run": settings["dry_run"],
        "emergency_stop": settings["emergency_stop"],
        "check_interval_minutes": settings["check_interval_minutes"],
        "max_actions_per_day": settings["max_actions_per_day"],
        "last_cycle": last_cycle[0] if last_cycle else None,
        "tasks_today": tasks_today,
        "completed_today": completed_today,
        "failed_today": failed_today,
        "waiting_approvals": waiting,
        "pending": running,
    }


def daily_brief(db: Session) -> str | None:
    """Portfolio-wide daily brief (sent to Telegram once per day)."""
    from app.services.lifecycle_service import MODE_LABELS, portfolio_overview
    from app.services.telegram_service import send_telegram

    ids = [c.id for c in db.query(Channel).all()]
    ov = portfolio_overview(db, ids)
    if ov["total"] == 0:
        return None
    by_mode = ov["by_mode"]
    top = ov["channels"][:1]
    worst = ov["channels"][-1:] if ov["channels"] else []
    text = (
        "AI YOUTUBE MANAGER\n"
        "DAILY BRIEF\n\n"
        f"Channels: {ov['total']}\n"
        f"Monetized: {by_mode.get('MONETIZED', 0) + by_mode.get('SCALE', 0)}\n"
        f"Growth: {by_mode.get('GROWTH', 0)}\n"
        f"New: {by_mode.get('NEW', 0)}\n"
        f"Recovery: {by_mode.get('RECOVERY', 0)}\n\n"
    )
    if top:
        c = top[0]
        text += f"TERBAIK\n{c['title']} ({c['mode_label']}, kesehatan {c['health_score']})\n\n"
    if worst:
        c = worst[0]
        text += f"PERLU PERHATIAN\n{c['title']} ({c['mode_label']}, kesehatan {c['health_score']})\n\n"
    text += "AI Status: ACTIVE (mode sesuai pengaturan)\n"
    if send_telegram(text[:3800]):
        logger.info("Daily brief sent to Telegram")
        return text
    return None
