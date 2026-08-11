"""Natural-language command router: user message -> agent + tools."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.ai.memory import require_channel
from app.ai.service import run_agent
from app.models.user import User
from app.utils.errors import AppError

# The AI occasionally echoes noise into its summary that duplicates the action
# cards already rendered by the frontend. Strip it so replies stay tidy.
_PERMISSION_ONLY = re.compile(
    r"^\s*(?:read|write|high_risk|high risk|approval|requires approval|requires_approval|"
    r"permission:\s*(?:read|write|high_risk))\.?\s*$",
    re.IGNORECASE,
)
_ACTION_HEADER = re.compile(
    r"^\s*(?:tindakan yang disarankan|tindakan|disarankan|rekomendasi tindakan|aksi yang disarankan|"
    r"recommended actions?|suggested actions?)\s*[:.]?\s*$",
    re.IGNORECASE,
)


def _clean_reply(text: str, labels: list[str] | None = None) -> str:
    """Remove AI noise from the reply text: permission-token lines, the
    'TINDAKAN YANG DISARANKAN' block, and duplicated action-label lines."""
    known = {lbl.strip() for lbl in (labels or []) if lbl and lbl.strip()}
    out: list[str] = []
    in_block = False
    for raw in text.split("\n"):
        line = raw.strip()
        if in_block:
            continue
        if _ACTION_HEADER.match(line):
            in_block = True  # drop the rest: it only re-lists the actions
            continue
        if _PERMISSION_ONLY.match(line):
            continue
        if line in known:
            continue
        out.append(raw)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return cleaned.strip()


# (regex, agent_key) in priority order
_COMMANDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(lapor|report|ringkas|hari ini|minggu ini)", re.I), "analytics_analyst"),
    (re.compile(r"(analis|analy|evaluasi|performa channel|channel saya)", re.I), "channel_analyst"),
    (re.compile(r"(judul|title)", re.I), "title_specialist"),
    (re.compile(r"(deskripsi|description)", re.I), "description_specialist"),
    (re.compile(r"(seo|keyword|tag)", re.I), "seo_specialist"),
    (re.compile(r"(content plan|ide video|10 ide|30 hari|konten)", re.I), "content_strategist"),
    (re.compile(r"(upload|publish|jadwal|private|visibility)", re.I), "publishing_manager"),
    (re.compile(r"(komentar|comment)", re.I), "comment_assistant"),
    (re.compile(r"(optimasi|ctr|terbaik|terburuk|rekomendasi|skor)", re.I), "decision_engine"),
]


def _pick_agent(message: str) -> str:
    for pattern, agent in _COMMANDS:
        if pattern.search(message):
            return agent
    return "youtube_manager"


async def handle_chat(db: Session, user: User, channel_id: str, message: str) -> dict:
    channel = require_channel(db, channel_id)
    if not channel_id:
        raise AppError(400, "VALIDATION_ERROR", "channel_id is required.")
    agent_key = _pick_agent(message)
    # run in a threadpool to avoid blocking the event loop
    import asyncio

    result = await asyncio.to_thread(run_agent, db, user, channel, agent_key, message)

    reply = result.get("summary") or "I analyzed your channel. See findings and recommendations below."
    if result.get("findings"):
        reply += "\n\n" + "\n".join(f"- {f}" for f in result["findings"][:5])
    if result.get("note"):
        reply += "\n\n" + result["note"]
    reply = _clean_reply(
        reply,
        [a.get("label") for a in result.get("actions", []) if isinstance(a, dict)],
    )

    return {
        "reply": reply,
        "actions": result.get("actions", []),
        "decisions": [
            {
                "decision_type": agent_key,
                "reasoning_summary": result.get("summary", ""),
                "recommendation": {"recommendations": result.get("recommendations", [])},
                "confidence": 0.7,
            }
        ],
        "task_id": result.get("task_id"),
    }
