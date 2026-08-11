from __future__ import annotations

from app.agents.permissions import PermissionGate, PermissionLevel
from app.agents.tools import TOOLS


def test_permission_ordering():
    assert PermissionLevel.READ < PermissionLevel.WRITE < PermissionLevel.HIGH_RISK


def test_gate_grants_read_write_not_high_risk():
    gate = PermissionGate()
    assert gate.can(PermissionLevel.READ)
    assert gate.can(PermissionLevel.WRITE)
    assert not gate.can(PermissionLevel.HIGH_RISK)


def test_tool_allowlist_complete():
    expected = {
        "get_channel_info", "get_channel_videos", "get_video_analytics",
        "get_channel_analytics", "get_traffic_sources", "search_channel_videos", "get_comments",
        "reply_comment",
        "create_video_draft", "update_video_metadata", "create_playlist",
        "schedule_upload", "upload_video", "generate_title",
        "generate_description", "generate_seo", "analyze_video",
        "analyze_channel", "create_content_plan",
    }
    assert set(TOOLS.keys()) == expected


def test_high_risk_never_auto_executes(db_session):
    from app.models.user import User
    from app.models.channel import Channel
    from app.agents.tools import execute_tool
    from app.services.approval_service import create_approval

    user = User(email="perm@example.com", name="Perm", password_hash="x")
    db_session.add(user)
    channel = Channel(
        youtube_account_id="acc-1", channel_id="chan-1", title="Test Channel"
    )
    db_session.add(channel)
    db_session.commit()
    db_session.refresh(channel)

    # upload_video never uploads and never creates approvals - it guides the
    # user to the Upload form instead.
    result = execute_tool(
        db_session, user, channel, "upload_video",
        {"title": "My Video", "description": "desc", "privacy_status": "private"},
    )
    assert "note" in result
