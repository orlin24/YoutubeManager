"""AI orchestration: run agents, generate titles/descriptions/SEO, log tasks."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.registry import AGENTS, load_system_prompt
from app.agents.tools import TOOLS
from app.ai.memory import build_context
from app.ai.provider import generate_structured, get_provider
from app.config import get_settings
from app.models.ai_decision import AiDecision
from app.models.ai_task import AiTask
from app.models.channel import Channel
from app.models.user import User
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.logging import get_logger

logger = get_logger("ai.service")


class AgentResponse(BaseModel):
    summary: str = ""
    findings: list[str] = []
    recommendations: list[str] = []
    actions: list[dict] = []


class _ReplyDraft(BaseModel):
    reply: str = ""


def _make_task(db: Session, channel_id: str | None, task_type: str, instruction: str) -> AiTask:
    task = AiTask(channel_id=channel_id, task_type=task_type, instruction=instruction, status="queued")
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _finish_task(db: Session, task: AiTask, result: dict | None = None, error: str | None = None) -> None:
    task.status = "failed" if error else "completed"
    task.error = error
    task.result = result
    task.completed_at = datetime.now(timezone.utc)
    db.commit()


def _log_decision(db: Session, *, channel_id, task_id, decision_type, summary, recommendation, confidence=0.0):
    decision = AiDecision(
        channel_id=channel_id,
        task_id=task_id,
        decision_type=decision_type,
        reasoning_summary=summary,
        recommendation=recommendation,
        confidence=confidence,
    )
    db.add(decision)
    db.commit()


def run_agent(
    db: Session, user: User, channel: Channel, agent_key: str, instruction: str, extra: dict | None = None
) -> dict:
    if agent_key not in AGENTS:
        raise AppError(400, "UNKNOWN_AGENT", f"Unknown agent: {agent_key}")
    if not get_settings().ai_enabled:
        # Graceful degradation: deterministic fallback using the decision engine.
        return _fallback_agent(db, channel, agent_key, instruction)

    task = _make_task(db, channel.id, agent_key, instruction)
    try:
        provider = get_provider()
        system_prompt = load_system_prompt(agent_key)
        context = build_context(
            db, channel, instruction,
            include_comments=agent_key == "comment_assistant",
            include_traffic=agent_key in ("analytics_analyst", "channel_analyst", "decision_engine"),
        )
        tool_names = ", ".join(AGENTS[agent_key]["tools"])
        user_prompt = (
            f"AVAILABLE TOOLS: {tool_names}\n\n"
            f"CONTEXT (JSON):\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"USER INSTRUCTION: {instruction}\n"
            + (f"\nEXTRA: {json.dumps(extra, ensure_ascii=False)}" if extra else "")
            + "\n\nRespond with strict JSON: {summary, findings[], recommendations[], actions[]}."
            + "Each action: {id, label, permission, requires_approval, payload}."
            + "\nThe summary must be clean analysis prose ONLY. NEVER list suggested actions inside the "
            + "summary, NEVER append permission words (read/write/high_risk) after action labels, and "
            + "NEVER write a 'TINDAKAN YANG DISARANKAN'/'RECOMMENDED ACTIONS' text section. All suggested "
            + "actions go ONLY into the actions array."
        )
        data = generate_structured(provider, system_prompt, user_prompt, AgentResponse)
        data = _normalize_actions(data)
        _finish_task(db, task, result=data)
        _log_decision(
            db,
            channel_id=channel.id,
            task_id=task.id,
            decision_type=agent_key,
            summary=data.get("summary", ""),
            recommendation={"recommendations": data.get("recommendations", [])},
            confidence=0.7,
        )
        log_audit(
            db,
            user_id=user.id,
            channel_id=channel.id,
            action="ai_agent_run",
            target=agent_key,
            result="ok",
            metadata={"task_id": task.id},
        )
        data["task_id"] = task.id
        return data
    except AppError:
        _finish_task(db, task, error="AI error")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Agent run failed", exc_info=exc)
        _finish_task(db, task, error=str(exc)[:500])
        raise AppError(500, "AI_RUN_FAILED", "The AI task failed.") from exc


def run_daily_report(
    db: Session, channel: Channel, task: AiTask, user: User | None = None
) -> dict:
    """Autonomous daily report: bind the analytics_analyst run to an already
    queued AiTask (created by the scheduler) instead of spawning a new one."""
    if not get_settings().ai_enabled:
        _finish_task(db, task, result={"summary": "AI disabled; daily report skipped."})
        return {"summary": "AI disabled; daily report skipped.", "task_id": task.id}

    task.status = "running"
    db.commit()
    try:
        provider = get_provider()
        system_prompt = load_system_prompt("analytics_analyst")
        report_format = load_system_prompt("daily_report")
        context = build_context(
            db, channel, task.instruction or "Produce today's channel report.",
            include_traffic=True,
        )
        # lifecycle mode + winners + priorities from the lifecycle engine (real data)
        try:
            from app.models.lifecycle import ChannelLifecycle
            from app.services.lifecycle_service import MODE_LABELS

            lc = db.query(ChannelLifecycle).filter_by(channel_id=channel.id).first()
            if lc is not None:
                context["channel_mode"] = {
                    "mode": lc.mode,
                    "mode_label": MODE_LABELS.get(lc.mode, lc.mode),
                    "objective": lc.objective,
                    "health_score": lc.health_score,
                    "winners": (lc.data or {}).get("winners", []),
                    "risk": (lc.data or {}).get("risk", {}),
                    "priorities": (lc.data or {}).get("priorities", []),
                }
        except Exception:  # noqa: BLE001 - lifecycle is a bonus, never break the report
            pass
        tool_names = ", ".join(AGENTS["analytics_analyst"]["tools"])
        user_prompt = (
            f"AVAILABLE TOOLS: {tool_names}\n\n"
            f"CONTEXT (JSON):\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"USER INSTRUCTION: {task.instruction or 'Produce today\'s channel report.'}\n\n"
            "Respond with strict JSON: {summary, findings[], recommendations[], actions[]}.\n"
            "The summary field MUST be the COMPLETE report text, written in Indonesian, "
            "following the FORMAT OUTPUT below exactly. findings/recommendations are optional extras.\n"
            f"FORMAT OUTPUT:\n{report_format}"
        )
        data = generate_structured(provider, system_prompt, user_prompt, AgentResponse)
        data = _normalize_actions(data)
        _finish_task(db, task, result=data)
        _log_decision(
            db,
            channel_id=channel.id,
            task_id=task.id,
            decision_type="daily_report",
            summary=data.get("summary", ""),
            recommendation={"recommendations": data.get("recommendations", [])},
            confidence=0.7,
        )
        log_audit(db, user_id=None, channel_id=channel.id, action="daily_report", result="ok")
        data["task_id"] = task.id
        return data
    except Exception as exc:  # noqa: BLE001
        logger.error("Daily report failed", exc_info=exc)
        _finish_task(db, task, error=str(exc)[:500])
        raise AppError(500, "AI_RUN_FAILED", "Daily report failed.") from exc


def generate_comment_reply(
    db: Session, channel: Channel, comment_text: str, author: str, video_title: str = ""
) -> str:
    """Draft a short, on-brand reply to one comment. Falls back to a template
    when AI is disabled or the provider errors, so the button always works."""
    fallback = f"Terima kasih sudah menonton dan berkomentar, {author}! 🙏 Dukungan Anda sangat berarti untuk channel ini."
    if not get_settings().ai_enabled:
        return fallback
    try:
        provider = get_provider()
        system_prompt = load_system_prompt("comment_assistant")
        user_prompt = (
            "Tulis SATU balasan komentar yang ramah, singkat (maks 2 kalimat), sesuai konteks "
            f"video '{video_title or 'video ini'}'. Penonton: {author}. Komentar: \"{comment_text}\"\n"
            "Balas hanya dengan teks balasannya - tanpa kutip, tanpa penjelasan."
        )
        data = generate_structured(provider, system_prompt, user_prompt, _ReplyDraft)
        return (data.get("reply") or fallback).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Comment reply draft failed, using fallback: %s", exc)
        return fallback


def _normalize_actions(data: dict, max_actions: int = 5) -> dict:
    """Clean AI-suggested actions: deduplicate by tool id, cap the count, and
    drop empty/pure-info READ noise so replies stay tidy."""
    actions = []
    seen: set[str] = set()
    for a in data.get("actions", []) or []:
        if not isinstance(a, dict):
            continue
        name = a.get("id") or a.get("tool") or a.get("label")
        if not name or not a.get("label"):
            continue
        if name in seen:
            continue  # deduplicate repeated tool suggestions (e.g. per-video)
        seen.add(name)
        permission = "READ"
        if name in TOOLS:
            permission = TOOLS[name].permission.name
        requires_approval = permission == "HIGH_RISK"
        actions.append(
            {
                "id": name,
                "label": a.get("label") or name,
                "permission": a.get("permission", permission),
                "requires_approval": a.get("requires_approval", requires_approval),
                "payload": a.get("payload", {}),
            }
        )
        if len(actions) >= max_actions:
            break
    data["actions"] = actions
    return data


def _fallback_agent(db: Session, channel: Channel, agent_key: str, instruction: str) -> dict:
    """Deterministic response when no AI provider is configured."""
    from app.agents.decision_engine import compute_video_score
    from app.agents.tools import TOOLS
    from app.ai.memory import get_profile
    from app.models.video import Video

    videos = db.query(Video).filter(Video.channel_id == channel.id).order_by(Video.view_count.desc()).limit(5).all()
    scored = [compute_video_score(v) for v in videos]
    valid = [s for s in scored if s.get("score") is not None]
    avg = round(sum(s["score"] for s in valid) / len(valid), 1) if valid else None
    profile = get_profile(db, channel.id)
    top = videos[0] if videos else None

    summary = (
        f"AI not configured (set AI_API_KEY to enable full analysis). Based on stored data: "
        f"channel {channel.title} has {channel.subscriber_count} subscribers and "
        f"{channel.video_count} videos. Average performance score: {avg if avg is not None else 'n/a'}."
    )
    findings = [f"Most viewed video: {top.title} ({top.view_count} views)" if top else "No videos synced yet."]
    recommendations = [
        "Connect a YouTube account and run a channel sync to get real analytics.",
        "Set AI_API_KEY in backend/.env to enable AI-powered analysis.",
        "Fill in the channel profile (niche, audience) for better context.",
    ]
    actions = []
    tool = TOOLS.get("analyze_channel")
    if tool:
        actions.append(
            {
                "id": "analyze_channel",
                "label": "Analyze channel performance",
                "permission": "READ",
                "requires_approval": False,
                "payload": {},
            }
        )
    return {
        "summary": summary,
        "findings": findings,
        "recommendations": recommendations,
        "actions": actions,
        "ai": False,
        "task_id": None,
        "note": "Deterministic fallback - no AI provider configured.",
    }


# ---------------------------------------------------------------------------
# Focused generators
# ---------------------------------------------------------------------------

_ID_WORDS = (
    "lagu", "yang", "untuk", "dengan", "tidak", "sedih", "cinta", "hati", "kerja",
    "perjalanan", "malaysia", "melayu", "terbaru", "nonstop", "full album", "dan",
    "dari", "ini", "kamu", "aku", "saat", "tanpa", "terbaik", "paling", "terpopuler",
    "rindu", "galau", "nangis", "mantan", "patah", "video", "jangan", "bikin", "mewek",
)


def _detect_lang(text: str | None) -> str:
    """Cheap language detection for titles: returns 'Bahasa Indonesia' or 'English'."""
    if text:
        lower = text.lower()
        if any(w in lower for w in _ID_WORDS):
            return "Bahasa Indonesia"
    return "English"


def _profile_lang(db: Session, channel: Channel) -> str | None:
    """Content language from the channel's AI memory (Memori AI).

    This is the source of truth: if the user set the content language in the
    channel profile, generation follows it - regardless of the title language.
    """
    from app.ai.memory import get_profile

    profile = get_profile(db, channel.id)
    if profile is None or not profile.language:
        return None
    lang = profile.language.strip().lower()
    if "english" in lang or "inggris" in lang:
        return "English"
    if "indones" in lang or "melayu" in lang:
        return "Bahasa Indonesia"
    return profile.language.strip()


def generate_titles(db: Session, channel: Channel, topic: str | None = None, video_id: str | None = None) -> list[str]:
    fallback = [
        "5 Cara " + (topic or "Meningkatkan Performa Channel") + " (Terbukti)",
        "Rahasia " + (topic or "Konten") + " yang Jarang Diketahui",
        "Tutorial " + (topic or "Lengkap") + " untuk Pemula",
        "Kenapa " + (topic or "Video Ini") + " Wajib Kamu Tonton",
        (topic or "Topik") + ": Panduan Praktis 2025",
    ]
    if not get_settings().ai_enabled:
        return fallback
    try:
        provider = get_provider()
        context = build_context(db, channel, f"Generate 5 compelling titles for {topic or 'this channel'}")
        lang = _profile_lang(db, channel) or _detect_lang(topic) or "Bahasa Indonesia"
        prompt = (
            f"Channel context:\n{json.dumps(context.get('channel_profile', {}), ensure_ascii=False)}\n\n"
            f"Topic: {topic or 'general best practices for this niche'}\n"
            f"LANGUAGE: write all titles in {lang} (the channel's content language).\n"
            "Generate 5 click-worthy, non-clickbait titles. Respond JSON: {\"titles\": [\"...\"]}"
        )
        data = generate_structured(provider, load_system_prompt("title_specialist"), prompt)
        titles = [t for t in data.get("titles", []) if isinstance(t, str)][:5]
        return titles or fallback
    except AppError as exc:
        logger.warning("generate_titles fallback: %s", exc.code)
        return fallback


def generate_description(db: Session, channel: Channel, title: str | None = None, topic: str | None = None) -> str:
    lang = _profile_lang(db, channel) or _detect_lang(title) or "Bahasa Indonesia"
    if lang == "Bahasa Indonesia":
        fallback = (
            f"{title or topic or 'Video'} - pada video ini kita bahas semuanya langkah demi "
            "langkah. Subscribe untuk konten serupa lainnya, dan pantau content plan untuk "
            "video berikutnya."
        )
    else:
        fallback = (
            f"{title or topic or 'Video'} - in this video we cover the essentials step by step. "
            "Subscribe for more content like this, and check the content plan for what's coming next."
        )
    if not get_settings().ai_enabled:
        return fallback
    try:
        provider = get_provider()
        prompt = (
            f"Video title: {title or topic or 'untitled'}\n"
            f"LANGUAGE: the channel's content language is {lang} - write the ENTIRE description in {lang}.\n"
            "Write a 3-4 paragraph description with keywords, timestamps placeholder and a CTA. "
            "Respond JSON: {\"description\": \"...\"}"
        )
        data = generate_structured(provider, load_system_prompt("description_specialist"), prompt)
        return data.get("description") or fallback
    except AppError as exc:
        logger.warning("generate_description fallback: %s", exc.code)
        return fallback


def generate_seo(db: Session, channel: Channel, title: str | None = None, description: str | None = None) -> dict:
    lang = _profile_lang(db, channel) or _detect_lang(title) or "Bahasa Indonesia"
    if lang == "Bahasa Indonesia":
        fallback = {
            "keywords": ["lagu malaysia", "lagu sedih", "lagu melayu", "full album"],
            "tags": ["lagu malaysia", "lagu sedih", "lagu melayu", "full album", "nonstop",
                     "slow rock", "balada", "nostalgia", (title or "video")[:30]],
            "ai": False,
        }
    else:
        fallback = {
            "keywords": [title.split()[0] if title else "youtube", "tutorial", "guide"],
            "tags": ["ai", "youtube manager", (title or "video")[:30]],
            "ai": False,
        }
    if not get_settings().ai_enabled:
        return fallback
    try:
        provider = get_provider()
        prompt = (
            f"Title: {title or ''}\nDescription: {(description or '')[:800]}\n"
            f"LANGUAGE: the channel's content language is {lang} - generate keywords and tags in {lang}.\n"
            "Generate 8 SEO keywords and 10 tags. Respond JSON: {\"keywords\": [...], \"tags\": [...]}"
        )
        data = generate_structured(provider, load_system_prompt("seo_specialist"), prompt)
        return {
            "keywords": data.get("keywords", fallback["keywords"])[:8],
            "tags": data.get("tags", fallback["tags"])[:10],
            "ai": True,
        }
    except AppError as exc:
        logger.warning("generate_seo fallback: %s", exc.code)
        return fallback


class ContentPattern(BaseModel):
    title: str = ""
    description: str = ""
    target_keyword: str = ""
    reason: str = ""


class ContentPatternResponse(BaseModel):
    analysis: str = ""
    recommendations: list[ContentPattern] = []


def generate_content_patterns(db: Session, channel: Channel, days: int = 28) -> dict:
    """Read proven performance (views by content + views by traffic source),
    then create 3 title/description recommendations and SAVE them to the
    content plan as SCHEDULED. Returns {analysis, recommendations, saved}."""
    from app.ai.memory import get_traffic_sources
    from app.models.video import Video

    if not get_settings().ai_enabled:
        raise AppError(503, "AI_DISABLED", "AI belum diaktifkan. Periksa kredensial AI provider.")

    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel.id)
        .order_by(Video.view_count.desc())
        .limit(10)
        .all()
    )
    video_rows = [
        {
            "title": v.title,
            "views": v.view_count,
            "likes": v.like_count,
            "comments": v.comment_count,
            "published_at": v.published_at.date().isoformat() if v.published_at else None,
            "privacy": v.privacy_status,
        }
        for v in videos
    ]
    traffic = get_traffic_sources(db, channel, days)
    traffic_rows = [{"label": t["label"], "views": t["views"], "percent": t["percent"]} for t in traffic]

    # baseline (audit #8): median views channel-wide so claims compare to reality
    all_views = [v.view_count for v in db.query(Video).filter(Video.channel_id == channel.id) if v.view_count]
    all_views.sort()
    median_views = (
        all_views[len(all_views) // 2]
        if all_views and len(all_views) % 2
        else ((all_views[len(all_views) // 2 - 1] + all_views[len(all_views) // 2]) / 2.0 if len(all_views) >= 2 else (all_views[0] if all_views else 0))
    )
    total_videos = len(all_views)
    # pattern repetition: how many top videos share a title prefix (audit #7)
    from collections import Counter

    prefix_counts = Counter((v.title or "").strip().lower()[:20] for v in videos if v.title)
    top_count = max(prefix_counts.values(), default=1)
    pattern_status = (
        "PROVEN" if total_videos >= 10 and top_count >= 10 and median_views and (videos[0].view_count or 0) >= median_views * 2
        else "PROMISING" if top_count >= 3 and median_views and (videos[0].view_count or 0) >= median_views * 1.5
        else "OUTLIER" if median_views and (videos[0].view_count or 0) >= median_views * 1.5
        else "INCONCLUSIVE"
    )
    confidence = {"PROVEN": "HIGH", "PROMISING": "MEDIUM", "OUTLIER": "LOW", "INCONCLUSIVE": "LOW"}[pattern_status]

    provider = get_provider()
    system_prompt = load_system_prompt("content_strategist")
    user_prompt = (
        "TUGAS: Analisis pola judul dari data channel ini dengan hati-hati.\n"
        "Gunakan data 'PENAYANGAN MENURUT KONTEN' (video + views) dan "
        "'PENAYANGAN MENURUT SUMBER TRAFFIC' (terutama Rekomendasi video) untuk "
        "menemukan pola judul/deskripsi yang layak DIUJI.\n"
        "PENTING (audit #21): SATU video viral BUKAN pola terbukti. "
        "Jangan pernah menulis 'video ini pasti berhasil'; tulis 'pola ini outperform baseline "
        "dan layak dijadikan kandidat eksperimen'. Sebutkan ekspektasi realistis.\n\n"
        f"BASELINE CHANNEL: median views {median_views:.0f} dari {total_videos} video. "
        f"Tingkat pengulangan pola judul: {top_count} video dari 10 teratas. "
        f"Status pola: {pattern_status} (confidence {confidence}).\n\n"
        f"PENAYANGAN MENURUT KONTEN (video dengan views tertinggi):\n{json.dumps(video_rows, ensure_ascii=False)}\n\n"
        f"PENAYANGAN MENURUT SUMBER TRAFFIC ({days} hari):\n{json.dumps(traffic_rows, ensure_ascii=False)}\n\n"
        "Buat TEPAT 3 rekomendasi judul + deskripsi sebagai KANDIDAT EKSPERIMEN. "
        "Setiap rekomendasi WAJIB berisi field 'reason' yang mengutip video nyata di atas "
        "(misal: 'karena judul \"X\" mendapat Y views lewat rekomendasi video, polanya adalah...') "
        "dan membandingkannya dengan median channel. "
        "Jangan mengarang angka di luar data yang diberikan. Kalau data belum cukup, katakan di 'analysis'.\n"
        "Respond strict JSON: {analysis, recommendations: [{title, description, target_keyword, reason}]} "
        "dalam Bahasa Indonesia."
    )
    data = generate_structured(provider, system_prompt, user_prompt, ContentPatternResponse)

    from datetime import date, timedelta

    from app.models.content_plan_item import ContentPlanItem

    analysis = str(data.get("analysis", "")).strip()
    recs: list[dict] = []
    for raw in data.get("recommendations", [])[:3]:
        if isinstance(raw, dict) and raw.get("title"):
            recs.append(
                {
                    "title": str(raw.get("title", "")).strip(),
                    "description": str(raw.get("description", "") or "").strip(),
                    "target_keyword": str(raw.get("target_keyword", "") or "").strip(),
                    "reason": str(raw.get("reason", "") or "").strip(),
                }
            )
    today = date.today()
    saved: list[dict] = []
    for idx, rec in enumerate(recs):
        item = ContentPlanItem(
            channel_id=channel.id,
            title=rec["title"],
            description=rec["description"] or None,
            target_keyword=rec["target_keyword"] or None,
            status="SCHEDULED",
            publish_date=today + timedelta(days=idx + 1),
            notes=rec["reason"] or None,
            idea=analysis[:500],
        )
        db.add(item)
        saved.append(
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "target_keyword": item.target_keyword,
                "reason": item.notes,
                "status": item.status,
                "publish_date": item.publish_date.isoformat(),
            }
        )
    db.commit()

    # automatic learning: record the recommendation so expected vs actual can be
    # compared later and confidence adjusted (audit #16). Expected value = 2x
    # channel median views - a realistic experiment target, not a promise.
    if saved and median_views:
        try:
            from app.services.learning_service import record_recommendation

            expected_value = median_views * 2.0
            record_recommendation(
                db, channel.id,
                decision=f"Uji pola judul: {saved[0]['title']}",
                reason=analysis[:300],
                evidence=f"Status pola {pattern_status}; median channel {median_views:.0f} views; {top_count} video teratas berbagi pola judul.",
                sample_size=total_videos,
                confidence=confidence,
                expected_outcome=f"Views >= 2x median channel ({expected_value:.0f})",
                expected_value=expected_value,
            )
        except Exception as exc:  # noqa: BLE001 - learning must never break pattern generation
            logger.warning("record_recommendation failed: %s", exc)

    logger.info("Saved %d content pattern item(s) for channel %s", len(saved), channel.channel_id)
    return {
        "analysis": analysis,
        "recommendations": recs,
        "saved": saved,
        "pattern_status": pattern_status,
        "confidence": confidence,
        "baseline": {"median": round(median_views, 1), "sample_size": total_videos},
    }
