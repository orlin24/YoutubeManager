from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["app"] == "AI YouTube Manager"
    checks = data["checks"]
    assert "backend" in checks
    assert checks["backend"] == "ok"
    assert checks["database"] in ("ok", "error")
    assert checks["youtube_api"] in ("configured", "not_configured", "error")
    assert checks["ai_provider"] in ("configured", "not_configured", "error")


def test_health_shape_stable(client):
    resp = client.get("/api/health")
    assert set(resp.json()["checks"].keys()) == {
        "backend", "database", "youtube_api", "ai_provider", "redis",
    }


def test_oauth_not_configured_message(client):
    resp = client.get("/api/auth/google")
    assert resp.status_code == 503
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_CONFIGURED"
    assert (
        body["error"]["message"]
        == "Google OAuth is not configured. Please configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
    )
