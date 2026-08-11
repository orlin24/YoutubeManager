"""Agent registry: agent key -> metadata + system prompt file."""
from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "system"

AGENTS: dict[str, dict] = {
    "youtube_manager": {
        "name": "YouTube Manager",
        "system_prompt_file": "youtube_manager.txt",
        "description": "General manager: overview, decisions, coordination.",
        "tools": [
            "get_channel_info", "get_channel_videos", "get_channel_analytics",
            "get_video_analytics", "search_channel_videos", "analyze_video",
            "analyze_channel", "create_video_draft", "create_content_plan",
        ],
    },
    "channel_analyst": {
        "name": "Channel Analyst",
        "system_prompt_file": "channel_analyst.txt",
        "description": "Deep channel performance analysis and recommendations.",
        "tools": ["get_channel_info", "get_channel_analytics", "get_channel_videos", "analyze_channel"],
    },
    "seo_specialist": {
        "name": "SEO Specialist",
        "system_prompt_file": "seo_specialist.txt",
        "description": "Titles, descriptions, keywords, tags.",
        "tools": ["generate_title", "generate_description", "generate_seo", "search_channel_videos"],
    },
    "content_strategist": {
        "name": "Content Strategist",
        "system_prompt_file": "content_strategist.txt",
        "description": "Content plans, ideas, schedules.",
        "tools": ["get_channel_info", "get_channel_analytics", "create_video_draft", "create_content_plan"],
    },
    "title_specialist": {
        "name": "Title Specialist",
        "system_prompt_file": "title_specialist.txt",
        "description": "High-CTR title generation.",
        "tools": ["generate_title", "search_channel_videos"],
    },
    "description_specialist": {
        "name": "Description Specialist",
        "system_prompt_file": "description_specialist.txt",
        "description": "Compelling descriptions with keywords.",
        "tools": ["generate_description"],
    },
    "analytics_analyst": {
        "name": "Analytics Analyst",
        "system_prompt_file": "analytics_analyst.txt",
        "description": "Reports, trends, underperformers, opportunities.",
        "tools": ["get_channel_analytics", "get_traffic_sources", "get_video_analytics", "get_channel_videos", "analyze_video", "analyze_channel"],
    },
    "daily_report": {
        "name": "Daily Report",
        "system_prompt_file": "daily_report.txt",
        "description": "Daily Telegram-format report (automated scheduler).",
        "tools": ["get_channel_analytics", "get_traffic_sources", "get_video_analytics", "get_channel_videos"],
    },
    "publishing_manager": {
        "name": "Publishing Manager",
        "system_prompt_file": "publishing_manager.txt",
        "description": "Uploads, scheduling, visibility.",
        "tools": ["schedule_upload", "upload_video", "get_channel_videos"],
    },
    "comment_assistant": {
        "name": "Comment Assistant",
        "system_prompt_file": "comment_assistant.txt",
        "description": "Comment responses and engagement ideas.",
        "tools": ["get_comments", "get_channel_videos"],
    },
    "decision_engine": {
        "name": "Decision Engine",
        "system_prompt_file": "decision_engine.txt",
        "description": "Scores videos and decides what to optimize.",
        "tools": ["analyze_video", "analyze_channel", "get_channel_analytics"],
    },
}


def load_system_prompt(agent_key: str) -> str:
    meta = AGENTS.get(agent_key)
    if meta is None:
        raise KeyError(agent_key)
    path = PROMPTS_DIR / meta["system_prompt_file"]
    return path.read_text(encoding="utf-8")
