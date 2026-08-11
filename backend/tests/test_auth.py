from __future__ import annotations

from app.auth.password import hash_password, verify_password


def test_setup_once_then_login_me_logout(client):
    # Fresh install: setup-status is required
    status = client.get("/api/auth/setup-status")
    assert status.status_code == 200
    assert status.json()["setup_required"] is True

    setup = client.post(
        "/api/auth/setup",
        json={"email": "alice@example.com", "name": "Alice", "password": "password123"},
    )
    assert setup.status_code == 201
    body = setup.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["access_token"]

    # After setup, setup-status flips to False
    status2 = client.get("/api/auth/setup-status")
    assert status2.json()["setup_required"] is False

    # Second setup must be rejected (one-time only)
    dup = client.post(
        "/api/auth/setup",
        json={"email": "bob@example.com", "name": "Bob", "password": "password123"},
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "ALREADY_SETUP"

    login = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]

    bad = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_CREDENTIALS"

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["id"] == body["user"]["id"]

    client.cookies.clear()  # drop session cookies to simulate an anonymous request
    me_no_token = client.get("/api/auth/me")
    assert me_no_token.status_code == 401
    assert me_no_token.json()["error"]["code"] == "UNAUTHORIZED"


def test_register_disabled(client):
    # The app has no public registration; /auth/register must not create accounts.
    resp = client.post(
        "/api/auth/register",
        json={"email": "x@example.com", "name": "X", "password": "password123"},
    )
    assert resp.status_code in (404, 405)
    assert "success" not in resp.json() or resp.json().get("success") is not True


def test_password_hashing():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_validation_error_envelope(client):
    resp = client.post("/api/auth/setup", json={"email": "x", "name": "X", "password": "short"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
