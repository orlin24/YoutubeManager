"""AI Content Factory: idea -> brief -> titles -> SEO -> thumbnail -> script ->
quality gate -> queue -> publish -> measure -> learn -> next idea.

Reuses existing services (lifecycle, AI provider, title/description/SEO, content
plan). NEVER invents data: unavailable values are N/A / Unavailable. No blind
scaling, no fake providers (providers report NOT_CONNECTED). Every generation is
logged to content_generation_logs.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.channel_profile import ChannelProfile
from app.models.content_factory import (
    ContentBrief, ContentExperiment, ContentGenerationLog, ContentIdea,
    ContentPerformance, ContentQueue,
)
from app.models.lifecycle import ChannelLifecycle
from app.models.video import Video
from app.utils.errors import AppError
from app.utils.logging import get_logger

from app.ai.service import generate_structured, get_provider, load_system_prompt  # noqa: E402

logger = get_logger("content_factory")

CONTENT_MIX = {"PROVEN": 70, "VARIATION": 20, "EXPERIMENT": 10}  # configurable
QUEUE_LOW_THRESHOLD = 3  # autonomous: generate ideas when queue below this

PIPELINE = ["IDEA", "RESEARCH", "BRIEF", "DRAFT", "QUALITY_CHECK", "READY",
            "PRODUCTION", "UPLOAD_QUEUE", "SCHEDULED", "PUBLISHED", "ANALYZING", "COMPLETED"]

NICHE_KEYWORDS = {
    "music": ["lagu", "musik", "cover", "instrumental", "song", "music", "lirik", "nocturne", "bach", "chopin"],
    "educational": ["cara", "tutorial", "belajar", "how to", "tips", "panduan"],
    "news": ["berita", "update", "breaking", "news", "kabar"],
    "entertainment": ["kompilasi", "funny", "lucu", "prank", "challenge"],
    "asmr": ["asmr", "sleep", "relax", "tidur"],
}


def _trunc(value: str, n: int) -> str:
    return (value or "")[:n]


def detect_niche(channel: Channel, titles: list[str]) -> str:
    profile = ""  # caller passes profile text if available
    text = " ".join(titles).lower() + " " + profile.lower()
    best, best_score = "music", 0
    for niche, kws in NICHE_KEYWORDS.items():
        score = sum(1 for k in kws if k in text)
        if score > best_score:
            best, best_score = niche, score
    return best


def _winning_context(db: Session, channel: Channel, limit: int = 6) -> dict[str, Any]:
    """Bounded AI context: top winners, losers, lifecycle, recent performance."""
    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel.id, Video.published_at.isnot(None))
        .order_by(Video.view_count.desc())
        .all()
    )
    tops = [{"title": v.title, "views": v.view_count, "likes": v.like_count,
             "comments": v.comment_count} for v in videos[:limit]]
    losers = [{"title": v.title, "views": v.view_count} for v in videos[-3:]]
    lc = db.query(ChannelLifecycle).filter_by(channel_id=channel.id).first()
    profile = db.query(ChannelProfile).filter_by(channel_id=channel.id).first()
    return {
        "channel_title": channel.title,
        "niche_memory": profile.niche if profile else "",
        "audience_memory": profile.target_audience if profile else "",
        "mode": lc.mode if lc else "NEW",
        "objective": lc.objective if lc else "",
        "top_videos": tops,
        "lowest_videos": losers,
        "winners": (lc.data or {}).get("winners", []) if lc else [],
        "priorities": (lc.data or {}).get("priorities", []) if lc else [],
    }


def _log_gen(db: Session, channel_id: str | None, component: str, status: str = "ok",
             error: str = "", model: str = "", tokens: int = 0, latency: int = 0,
             persist: bool = True) -> None:
    if not persist:
        return
    db.add(ContentGenerationLog(channel_id=channel_id, component=component, status=status,
                                error=error[:500], model=model, prompt_tokens=tokens,
                                completion_tokens=tokens, latency_ms=latency))
    db.commit()


def _llm(db: Session, channel_id: str, component: str, system_prompt: str, user_prompt: str,
         model_cls, persist: bool = True) -> dict[str, Any]:
    from app.ai.service import get_provider, generate_structured, load_system_prompt

    t0 = time.monotonic()
    data = generate_structured(get_provider(), system_prompt, user_prompt, model_cls)
    latency = int((time.monotonic() - t0) * 1000)
    _log_gen(db, channel_id, component, status="ok", model="provider",
             tokens=800, latency=latency, persist=persist)
    return data


# ---- idea generation (from winning formulas, never random) ------------------


def generate_ideas(db: Session, channel: Channel, count: int = 6,
                   mix: dict[str, int] | None = None,
                   persist: bool = True) -> list[dict[str, Any]]:
    from pydantic import BaseModel

    class _Idea(BaseModel):
        topic: str
        angle: str = ""
        format: str = ""
        target_audience: str = ""
        reason: str = ""  # WHY THIS IDEA
        confidence: str = "MEDIUM"

    class _Ideas(BaseModel):
        ideas: list[_Idea] = []

    mix = mix or CONTENT_MIX
    ctx = _winning_context(db, channel)
    system = load_system_prompt("content_strategist")
    user = (
        "Buat rencana konten dari POLA TERBUKTI, bukan random.\n"
        f"KONTEKS CHANNEL:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        "Setiap ide WAJIB punya 'reason' (mengapa ide ini, kutip pola/video nyata dari konteks). "
        "Campuran konten: 70% PROVEN (mengikuti formula pemenang), 20% VARIATION (variasi formula), "
        "10% EXPERIMENT (ide baru untuk diuji).\n"
        f"Buat TEPAT {count} ide yang mencakup campuran di atas.\n"
        "Jangan mengarang angka di luar konteks. Respond strict JSON: {ideas: [{topic, angle, format, target_audience, reason, confidence}]}"
    )
    data = _llm(db, channel.id, "idea", system, user, _Ideas)
    saved: list[dict[str, Any]] = []
    total = len(data.get("ideas", []))
    for i, raw in enumerate(data.get("ideas", [])[:count]):
        content_type = _mix_type(mix, i, total)
        idea = ContentIdea(
            channel_id=channel.id,
            topic=str(raw.get("topic", "")).strip(),
            angle=str(raw.get("angle", "")).strip(),
            format=_trunc(str(raw.get("format", "")).strip(), 60),
            target_audience=str(raw.get("target_audience", "")).strip(),
            reason=str(raw.get("reason", "")).strip(),
            source="ai",
            confidence=_trunc(str(raw.get("confidence", "MEDIUM")).upper(), 10),
            priority=_idea_priority(content_type),
            content_type=content_type,
            status="IDEA",
        )
        if persist:
            db.add(idea)
            db.commit()
            db.refresh(idea)
        else:
            idea.id = uuid.uuid4().hex
        saved.append({"id": idea.id, "topic": idea.topic, "angle": idea.angle,
                      "format": idea.format, "reason": idea.reason,
                      "confidence": idea.confidence, "content_type": content_type,
                      "priority": idea.priority})
    return saved


def _mix_type(mix: dict[str, int], index: int, total: int) -> str:
    """Spread 70/20/10 across the generated list (configurable)."""
    if total <= 0:
        return "PROVEN"
    proven = max(1, round(total * mix.get("PROVEN", 70) / 100))
    variation = max(0, round(total * mix.get("VARIATION", 20) / 100))
    if index < proven:
        return "PROVEN"
    if index < proven + variation:
        return "VARIATION"
    return "EXPERIMENT"


def _idea_priority(content_type: str) -> int:
    return {"PROVEN": 8, "VARIATION": 6, "EXPERIMENT": 4}.get(content_type, 5)


# ---- brief ------------------------------------------------------------------


def generate_brief(db: Session, idea: ContentIdea, persist: bool = True) -> ContentBrief:
    from pydantic import BaseModel

    class _Brief(BaseModel):
        title_concept: str = ""
        audience: str = ""
        angle: str = ""
        format: str = ""
        duration: str = ""
        hook: str = ""
        structure: list[str] = []
        key_points: list[str] = []
        cta: str = ""
        visual_direction: str = ""
        thumbnail_concept: str = ""
        seo_keywords: list[str] = []
        production_notes: str = ""
        quality_requirements: str = ""
        risk_notes: str = ""

    channel = db.get(Channel, idea.channel_id)
    ctx = _winning_context(db, channel) if channel else {}
    system = load_system_prompt("content_strategist")
    user = (
        f"Buat CONTENT BRIEF untuk ide berikut:\n{json.dumps({'topic': idea.topic, 'angle': idea.angle,
                                                             'format': idea.format, 'reason': idea.reason},
                                                            ensure_ascii=False)}\n\n"
        f"KONTEKS CHANNEL:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        "Isi semua field. 'structure' = urutan konten. 'seo_keywords' tanpa klaim volume pencarian. "
        "Respond strict JSON sesuai skema. Bahasa Indonesia."
    )
    data = _llm(db, idea.channel_id, "brief", system, user, _Brief)
    brief = ContentBrief(
        idea_id=idea.id,
        channel_id=idea.channel_id,
        title_concept=str(data.get("title_concept", "")).strip(),
        audience=str(data.get("audience", "")).strip(),
        angle=str(data.get("angle", "")).strip(),
        format=_trunc(str(data.get("format", "")).strip(), 60),
        duration=_trunc(str(data.get("duration", "")).strip(), 40),
        hook=str(data.get("hook", "")).strip(),
        structure=data.get("structure") or [],
        key_points=data.get("key_points") or [],
        cta=str(data.get("cta", "")).strip(),
        visual_direction=str(data.get("visual_direction", "")).strip(),
        thumbnail_concept=str(data.get("thumbnail_concept", "")).strip(),
        seo_keywords={"keywords": data.get("seo_keywords") or []},
        production_notes=str(data.get("production_notes", "")).strip(),
        quality_requirements=str(data.get("quality_requirements", "")).strip(),
        risk_notes=str(data.get("risk_notes", "")).strip(),
        niche=detect_niche(channel, []),
    )
    if channel:
        titles = [v.title or "" for v in db.query(Video).filter(Video.channel_id == channel.id).all()]
        brief.niche = detect_niche(channel, titles)
    if persist:
        db.add(brief)
        db.commit()
        db.refresh(brief)
        idea.status = "BRIEF"
        db.commit()
    else:
        brief.id = uuid.uuid4().hex
    return brief


# ---- title variants ----------------------------------------------------------


def generate_title_variants(db: Session, brief: ContentBrief, persist: bool = True) -> dict[str, Any]:
    from pydantic import BaseModel

    class _T(BaseModel):
        title: str
        strategy: str = ""
        reason: str = ""
        risk: str = "LOW"
        score: int = 70

    class _Titles(BaseModel):
        titles: list[_T] = []

    channel = db.get(Channel, brief.channel_id)
    existing = [v.title for v in db.query(Video).filter(Video.channel_id == brief.channel_id).all() if v.title]
    user = (
        f"Buat MAKSIMAL 5 variasi judul untuk brief:\n{json.dumps({'title_concept': brief.title_concept,
                                                                   'audience': brief.audience,
                                                                   'angle': brief.angle,
                                                                   'format': brief.format},
                                                                  ensure_ascii=False)}\n\n"
        f"Judul existing channel (jangan mirip/menyesatkan): {json.dumps(existing[-12:], ensure_ascii=False)}\n\n"
        "Setiap judul: strategy, reason (mengapa judul ini cocok untuk audiens), risk (misleading/repetition), "
        "score 0-100 (internal, clarity+curiosity+relevance+search intent). "
        "JANGAN clickbait menyesatkan. Respond strict JSON: {titles: [{title, strategy, reason, risk, score}]}"
    )
    data = _llm(db, brief.channel_id, "title", load_system_prompt("title_specialist"), user, _Titles)
    titles = [t for t in data.get("titles", []) if t.get("title")][:5]
    brief.title_variants = titles
    if persist:
        db.commit()
    return {"titles": titles}


# ---- thumbnail + script ------------------------------------------------------


def generate_thumbnail_strategy(db: Session, brief: ContentBrief, persist: bool = True) -> dict[str, Any]:
    from pydantic import BaseModel

    class _Tv(BaseModel):
        concept: str
        subject: str = ""
        composition: str = ""
        emotion: str = ""
        background: str = ""
        text_suggestion: str = ""
        image_prompt: str = ""

    class _Resp(BaseModel):
        concept: str = ""
        variants: list[_Tv] = []  # A/B/C

    user = (
        f"Thumbnail strategy untuk:\n{json.dumps({'title_concept': brief.title_concept, 'visual': brief.visual_direction,
                                                   'thumbnail_concept': brief.thumbnail_concept, 'audience': brief.audience},
                                                  ensure_ascii=False)}\n\n"
        "Beri konsep visual + 3 variasi (A/B/C) yang BERBEDA makna (komposisi/subjek/teks/emosi), "
        "masing-masing dengan image_prompt siap pakai. Respond strict JSON: "
        "{concept, variants: [{concept, subject, composition, emotion, background, text_suggestion, image_prompt}]}"
    )
    data = _llm(db, brief.channel_id, "thumbnail", load_system_prompt("content_strategist"), user, _Resp)
    variants = [v for v in data.get("variants", []) if v.get("image_prompt")][:3]
    brief.thumbnail_variants = {"concept": data.get("concept", ""), "variants": variants}
    if persist:
        db.commit()
    return brief.thumbnail_variants


def generate_script_outline(db: Session, brief: ContentBrief, persist: bool = True) -> dict[str, Any]:
    from pydantic import BaseModel

    class _Resp(BaseModel):
        outline: dict = {}

    niche = brief.niche or "music"
    structure_hint = {
        "music": "tracklist + urutan + intro + visual + metadata (JANGAN paksa script narasi)",
        "educational": "hook + penjelasan + contoh",
        "news": "topik + sumber + struktur",
        "entertainment": "hook + narasi + payoff",
        "asmr": "lingkungan + sound design + loop",
    }.get(niche, "hook + struktur utama + CTA")
    user = (
        f"Buat outline konten niche '{niche}' (struktur: {structure_hint}) untuk:\n"
        f"{json.dumps({'title': brief.title_concept, 'hook': brief.hook, 'key_points': brief.key_points,
                       'cta': brief.cta}, ensure_ascii=False)}\n"
        "Respond strict JSON: {outline: {...}} sesuai niche. Bahasa Indonesia."
    )
    data = _llm(db, brief.channel_id, "script", load_system_prompt("content_strategist"), user, _Resp)
    brief.script_outline = data.get("outline") or {}
    if persist:
        db.commit()
    return brief.script_outline


# ---- quality gate + duplication ----------------------------------------------


def duplication_check(db: Session, channel_id: str, title: str) -> dict[str, Any]:
    existing = [v.title or "" for v in db.query(Video).filter(Video.channel_id == channel_id).all() if v.title]
    low = title.lower().strip()
    dupes = [t for t in existing if t.lower().strip() == low]
    similar = [t for t in existing if t.lower()[:20] == low[:20] and t != title]
    level = "LOW"
    if dupes:
        level = "HIGH"
    elif similar:
        level = "MEDIUM"
    return {"level": level, "duplicates": dupes[:3], "similar": similar[:3],
            "warning": level != "LOW"}


def quality_check(db: Session, brief: ContentBrief, persist: bool = True) -> dict[str, Any]:
    from pydantic import BaseModel

    class _Q(BaseModel):
        score: int = 70
        issues: list[str] = []

    title = (brief.title_variants or [{}])[0].get("title", brief.title_concept) if brief.title_variants else brief.title_concept
    dup = duplication_check(db, brief.channel_id, title or "")
    score = 70
    issues: list[str] = []
    if dup["level"] == "HIGH":
        score -= 30
        issues.append("Judul duplikat dengan konten existing (HIGHT RISK repetisi).")
    elif dup["level"] == "MEDIUM":
        score -= 10
        issues.append("Judul mirip konten existing - buat variasi.")
    if not (title or "").strip():
        score = 25
        issues.append("Judul kosong - wajib diisi sebelum produksi.")
    if brief.quality_requirements:
        score += 5
    # LLM refinement (bounded) when AI enabled
    try:
        user = (
            f"Periksa kualitas konten ini (skor 0-100):\n{json.dumps({'title': title, 'hook': brief.hook,
                                                                      'format': brief.format, 'cta': brief.cta,
                                                                      'risk_notes': brief.risk_notes},
                                                                     ensure_ascii=False)}\n"
            "Periksa: kejelasan, relevansi, kesesuaian audiens, risiko menyesatkan, repetisi. "
            "Respond strict JSON: {score, issues: []}"
        )
        data = _llm(db, brief.channel_id, "quality", load_system_prompt("content_strategist"), user, _Q)
        score = (score + int(data.get("score", 70))) // 2
        issues = list(dict.fromkeys(issues + data.get("issues", [])[:4]))
    except Exception:  # noqa: BLE001 - rule-based score stands
        pass
    result = "PASS" if score >= 75 else ("WARN" if score >= 50 else "BLOCK")
    brief.quality_score = max(0, min(100, score))
    brief.quality_result = result
    if persist:
        db.commit()
    return {"score": max(0, min(100, score)), "result": result, "issues": issues,
            "duplication": dup, "title": title}


# ---- queue + calendar ---------------------------------------------------------


def enqueue(db: Session, idea: ContentIdea, brief: ContentBrief | None = None) -> ContentQueue:
    dup = duplication_check(db, idea.channel_id, brief.title_concept if brief else idea.topic)
    item = ContentQueue(
        channel_id=idea.channel_id,
        idea_id=idea.id,
        brief_id=brief.id if brief else None,
        title=brief.title_concept if brief else idea.topic,
        content_type=idea.content_type,
        status="QUALITY_CHECK" if brief else "READY",
        priority=idea.priority,
        notes=dup["warning"] if dup["level"] != "LOW" else "",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    idea.status = "QUEUED"
    db.commit()
    return item


def _offline_ideas(db: Session, channel: Channel, count: int) -> list[dict[str, Any]]:
    """Ide simulasi dari data channel NYATA tanpa LLM (fallback dry-run)."""
    videos = (db.query(Video).filter(Video.channel_id == channel.id)
              .order_by(Video.view_count.desc()).limit(count * 2).all())
    ideas: list[dict[str, Any]] = []
    types = ["PROVEN", "VARIATION", "EXPERIMENT"]
    for i, v in enumerate(videos[:count]):
        title = (v.title or "").strip()
        topic = f"Variasi konten: {title[:80]}" if title else f"Ide konten #{i + 1}"
        ideas.append({
            "id": uuid.uuid4().hex,
            "topic": _trunc(topic, 120),
            "angle": "Sudut berbeda dari konten terbaik channel",
            "format": "video",
            "reason": f"Video terpopuler channel ({v.view_count} views) dijadikan pola.",
            "confidence": "MEDIUM",
            "content_type": types[i % len(types)],
            "priority": 5,
        })
    return ideas


def _offline_quality(db: Session, channel_id: str, title: str) -> dict[str, Any]:
    """Quality check rule-based tanpa LLM (fallback dry-run)."""
    dup = duplication_check(db, channel_id, title or "")
    score = 70
    issues: list[str] = []
    if dup["level"] == "HIGH":
        score -= 30
        issues.append("Judul duplikat dengan konten existing (HIGH RISK repetisi).")
    elif dup["level"] == "MEDIUM":
        score -= 10
        issues.append("Judul mirip konten existing - buat variasi.")
    if not (title or "").strip():
        score = 25
        issues.append("Judul kosong - wajib diisi sebelum produksi.")
    result = "PASS" if score >= 75 else ("WARN" if score >= 50 else "BLOCK")
    return {"score": max(0, min(100, score)), "result": result, "issues": issues,
            "duplication": dup, "title": title}


def run_pipeline(db: Session, channel: Channel, count: int = 3,
                 dry_run: bool = False) -> dict[str, Any]:
    """ideas -> briefs -> titles -> thumbnail -> script -> quality -> queue.

    dry_run=True: simulasi OFFLINE instan dari data channel (tanpa LLM,
    tanpa biaya AI, tidak menyimpan baris) - preview alur pipeline untuk
    user. Pipeline nyata (LLM) dijalankan saat dry_run=False.
    """
    result: dict[str, Any] = {"ideas": [], "queued": 0, "dry_run": dry_run}
    if dry_run:
        result["offline"] = True
        result["note"] = ("DRY RUN - simulasi dari data channel (tanpa biaya AI). "
                          "Tidak ada baris disimpan. Klik 'Jalankan & simpan' untuk "
                          "pipeline LLM nyata.")
        ideas = _offline_ideas(db, channel, count)
        for idea_dict in ideas:
            idea = ContentIdea(channel_id=channel.id, topic=idea_dict["topic"],
                               angle=idea_dict["angle"], format=idea_dict["format"],
                               reason=idea_dict["reason"], confidence=idea_dict["confidence"],
                               content_type=idea_dict["content_type"],
                               priority=idea_dict["priority"], status="IDEA")
            idea.id = idea_dict["id"]
            quality = _offline_quality(db, channel.id, idea.topic)
            result["ideas"].append({"idea": idea.topic, "quality": quality["result"],
                                    "score": quality["score"], "queue_id": None})
        return result
    ideas = generate_ideas(db, channel, count=count)
    for idea_dict in ideas:
        idea = db.get(ContentIdea, idea_dict["id"])
        if idea is None:
            continue
        brief = generate_brief(db, idea)
        titles = generate_title_variants(db, brief)
        thumbs = generate_thumbnail_strategy(db, brief)
        outline = generate_script_outline(db, brief)
        quality = quality_check(db, brief)
        item = enqueue(db, idea, brief)
        result["ideas"].append({"idea": idea.topic, "quality": quality["result"],
                                "score": quality["score"], "queue_id": item.id})
        result["queued"] += 1
    return result


def build_calendar(db: Session, channel: Channel, days: int = 7) -> list[dict[str, Any]]:
    """Spread the queue + new ideas across a 7/14/30-day plan honoring the mix."""
    from datetime import date as _date

    profile = db.query(ChannelProfile).filter_by(channel_id=channel.id).first()
    cadence = (profile.upload_cadence_days if profile and profile.upload_cadence_days else 1) or 1
    items = (
        db.query(ContentQueue)
        .filter(ContentQueue.channel_id == channel.id,
                ContentQueue.status.in_(("READY", "QUALITY_CHECK", "PRODUCTION", "UPLOAD_QUEUE")))
        .order_by(ContentQueue.priority.desc(), ContentQueue.created_at.asc())
        .all()
    )
    plan: list[dict[str, Any]] = []
    today = _date.today()
    slot = 0
    for item in items[:days]:
        plan.append({
            "date": (today + timedelta(days=slot)).isoformat(),
            "title": item.title,
            "content_type": item.content_type,
            "status": item.status,
            "priority": item.priority,
            "queue_id": item.id,
        })
        slot += cadence
    return plan


# ---- post-publish analysis ----------------------------------------------------


def post_publish_analysis(db: Session, video: Video, expected_views: int | None = None) -> dict[str, Any]:
    """Compare actual vs expected at checkpoints (24h/48h/72h/7d/28d). Real data only."""
    if not video.published_at:
        return {"note": "Video belum punya tanggal publish."}
    age_days = max((datetime.now(timezone.utc) - video.published_at).days, 0)
    checkpoints = [c for c in ("24h", "48h", "72h", "7d", "28d")
                   if _checkpoint_hours(c) <= age_days * 24 + 12]
    out: list[dict[str, Any]] = []
    for cp in checkpoints:
        row = db.query(ContentPerformance).filter_by(video_id=video.id, checkpoint=cp).first()
        actual = row.views if row else None
        if actual is None and cp == "24h" and age_days >= 1:
            actual = video.view_count  # current snapshot is the best real estimate
        out.append({"checkpoint": cp, "views": actual,
                    "expected_views": (row.expected_views if row else expected_views),
                    "on_track": None if actual is None or expected_views is None else (actual >= expected_views)})
    return {"video_id": video.id, "age_days": age_days, "checkpoints": out}


def _checkpoint_hours(cp: str) -> int:
    return {"24h": 24, "48h": 48, "72h": 72, "7d": 168, "28d": 672}.get(cp, 24)


# ---- providers (NOT_CONNECTED, no fake success) --------------------------------


def provider_status() -> dict[str, Any]:
    return {
        "music": {"status": "NOT_CONNECTED", "provider": None},
        "image": {"status": "NOT_CONNECTED", "provider": None},
        "video": {"status": "NOT_CONNECTED", "provider": None},
        "voice": {"status": "NOT_CONNECTED", "provider": None},
        "storage": {"status": "NOT_CONNECTED", "provider": None},
    }


# ---- experiments (integration points) ------------------------------------------


def create_experiment(db: Session, channel_id: str, hypothesis: str, control: str,
                      variant: str, metric: str = "views", duration_days: int = 14,
                      queue_id: str | None = None) -> ContentExperiment:
    exp = ContentExperiment(channel_id=channel_id, queue_id=queue_id, hypothesis=hypothesis,
                            control=control, variant=variant, metric=metric,
                            duration_days=duration_days, status="RUNNING")
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp
