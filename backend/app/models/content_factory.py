"""Content Factory database: ideas, briefs, queue, experiments, performance, logs.

Content pipeline statuses (content_queue.status):
IDEA -> RESEARCH -> BRIEF -> DRAFT -> QUALITY_CHECK -> READY -> PRODUCTION ->
UPLOAD_QUEUE -> SCHEDULED -> PUBLISHED -> ANALYZING -> COMPLETED
plus FAILED / CANCELLED.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ID = {"default": lambda: __import__("uuid").uuid4().hex}


class ContentIdea(Base):
    __tablename__ = "content_ideas"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=ID["default"])
    channel_id: Mapped[str] = mapped_column(Text, index=True)
    topic: Mapped[str] = mapped_column(Text)
    angle: Mapped[str] = mapped_column(Text, default="")
    format: Mapped[str] = mapped_column(String(60), default="")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")  # WHY THIS IDEA
    source: Mapped[str] = mapped_column(String(40), default="ai")  # ai|manual|trend|experiment
    confidence: Mapped[str] = mapped_column(String(10), default="MEDIUM")  # LOW/MEDIUM/HIGH
    priority: Mapped[int] = mapped_column(Integer, default=5)
    content_type: Mapped[str] = mapped_column(String(20), default="PROVEN")  # PROVEN/VARIATION/EXPERIMENT
    status: Mapped[str] = mapped_column(String(20), default="IDEA")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentBrief(Base):
    __tablename__ = "content_briefs"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=ID["default"])
    idea_id: Mapped[str] = mapped_column(Text, index=True)
    channel_id: Mapped[str] = mapped_column(Text, index=True)
    title_concept: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(Text, default="")
    angle: Mapped[str] = mapped_column(Text, default="")
    format: Mapped[str] = mapped_column(String(60), default="")
    duration: Mapped[str] = mapped_column(String(40), default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    structure: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    key_points: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cta: Mapped[str] = mapped_column(Text, default="")
    visual_direction: Mapped[str] = mapped_column(Text, default="")
    thumbnail_concept: Mapped[str] = mapped_column(Text, default="")
    seo_keywords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    production_notes: Mapped[str] = mapped_column(Text, default="")
    quality_requirements: Mapped[str] = mapped_column(Text, default="")
    risk_notes: Mapped[str] = mapped_column(Text, default="")
    niche: Mapped[str] = mapped_column(String(40), default="")  # music|educational|news|entertainment|asmr
    script_outline: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    title_variants: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 5 titles + score
    thumbnail_variants: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # A/B/C prompts
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # internal 0-100
    quality_result: Mapped[str | None] = mapped_column(String(10), nullable=True)  # PASS/WARN/BLOCK
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentQueue(Base):
    __tablename__ = "content_queue"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=ID["default"])
    channel_id: Mapped[str] = mapped_column(Text, index=True)
    idea_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(20), default="PROVEN")
    status: Mapped[str] = mapped_column(String(30), default="IDEA")  # pipeline states
    priority: Mapped[int] = mapped_column(Integer, default=5)
    publish_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentExperiment(Base):
    __tablename__ = "content_experiments"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=ID["default"])
    channel_id: Mapped[str] = mapped_column(Text, index=True)
    queue_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    control: Mapped[str] = mapped_column(Text, default="")
    variant: Mapped[str] = mapped_column(Text, default="")
    metric: Mapped[str] = mapped_column(String(40), default="views")
    duration_days: Mapped[int] = mapped_column(Integer, default=14)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")  # RUNNING/WIN/LOSS/INCONCLUSIVE
    result: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(10), default="LOW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentPerformance(Base):
    __tablename__ = "content_performance"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=ID["default"])
    channel_id: Mapped[str] = mapped_column(Text, index=True)
    video_id: Mapped[str] = mapped_column(Text, index=True)
    checkpoint: Mapped[str] = mapped_column(String(10))  # 24h|48h|72h|7d|28d
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    watch_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention: Mapped[float | None] = mapped_column(Float, nullable=True)
    subscribers_gained: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    rpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    traffic_source: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentGenerationLog(Base):
    __tablename__ = "content_generation_logs"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=ID["default"])
    channel_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    component: Mapped[str] = mapped_column(String(40))  # idea|brief|title|seo|thumbnail|script|quality
    model: Mapped[str] = mapped_column(String(80), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok|error
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
