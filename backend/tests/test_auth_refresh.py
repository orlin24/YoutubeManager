"""Tests: the silent session-refresh endpoint (fixes forced re-login every 60 min)."""
from __future__ import annotations


def test_refresh_without_cookie_401(client):
    # no setup/login -> no refresh cookie -> 401 SESSION_EXPIRED
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SESSION_EXPIRED"


def test_refresh_exchanges_cookie(client):
    # setup + login to obtain the refresh cookie
    client.post("/api/auth/setup", json={
        "email": "owner@example.com", "name": "Owner", "password": "password123"})
    login = client.post("/api/auth/login", json={
        "email": "owner@example.com", "password": "password123"})
    assert login.status_code == 200
    assert "aym_refresh" in login.cookies

    # use the refresh cookie to get a fresh access token
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "owner@example.com"
    assert "aym_access" in r.cookies
    # new access token works for authenticated calls
    me = client.get("/api/auth/me")
    assert me.status_code == 200
