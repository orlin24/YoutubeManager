"""Import all models so Base.metadata is complete (used by Alembic + create_all)."""
from app.models.ai_decision import AiDecision
from app.models.ai_task import AiTask
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.app_setting import AppSetting
from app.models.approval_request import ApprovalRequest
from app.models.audit_log import AuditLog
from app.models.channel import Channel
from app.models.channel_profile import ChannelProfile
from app.models.content_plan_item import ContentPlanItem, CONTENT_PLAN_STATUSES
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

__all__ = [
    "AiDecision",
    "AiTask",
    "AnalyticsSnapshot",
    "AppSetting",
    "ApprovalRequest",
    "AuditLog",
    "Channel",
    "ChannelProfile",
    "ChannelLifecycle",
    "AiPattern",
    "ContentPlanItem",
    "CONTENT_PLAN_STATUSES",
    "User",
    "Video",
    "YouTubeAccount",
]
