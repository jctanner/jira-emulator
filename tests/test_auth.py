"""Tests for authentication endpoints (session login, myself, user creation, password change)."""

import httpx
import pytest

from tests.conftest import AUTH_HEADER


async def test_session_login_returns_jsessionid(client: httpx.AsyncClient):
    """POST /rest/auth/1/session with correct credentials should return a JSESSIONID."""
    resp = await client.post(
        "/rest/auth/1/session",
        json={"username": "admin", "password": "admin"},
    )
    assert resp.status_code == 200

    data = resp.json()
    assert "session" in data
    assert data["session"]["name"] == "JSESSIONID"
    assert isinstance(data["session"]["value"], str)
    assert len(data["session"]["value"]) > 0

    assert "loginInfo" in data
    assert data["loginInfo"]["loginCount"] == 1


async def test_get_myself_returns_current_user(client: httpx.AsyncClient):
    """GET /rest/api/2/myself should return info about the authenticated user."""
    resp = await client.get("/rest/api/2/myself", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert data["name"] == "admin"
    assert data["key"] == "admin"
    assert data["displayName"] == "Admin User"
    assert data["active"] is True
    assert "self" in data
    assert "accountId" in data


async def test_create_user(client: httpx.AsyncClient):
    """POST /rest/api/2/user should create a new user and return its details."""
    resp = await client.post(
        "/rest/api/2/user",
        json={
            "name": "testuser",
            "displayName": "Test User",
            "emailAddress": "test@example.com",
            "password": "testpass",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201

    data = resp.json()
    assert data["name"] == "testuser"
    assert data["displayName"] == "Test User"
    assert data["emailAddress"] == "test@example.com"
    assert data["active"] is True


async def test_create_duplicate_user_fails(client: httpx.AsyncClient):
    """Creating a user with an existing username should return 400."""
    user_data = {
        "name": "dupuser",
        "displayName": "Dup User",
        "emailAddress": "dup@example.com",
        "password": "pass123",
    }
    resp1 = await client.post("/rest/api/2/user", json=user_data, headers=AUTH_HEADER)
    assert resp1.status_code == 201

    resp2 = await client.post("/rest/api/2/user", json=user_data, headers=AUTH_HEADER)
    assert resp2.status_code == 400


async def test_change_own_password(client: httpx.AsyncClient):
    """PUT /rest/api/2/myself/password should return 204 on success."""
    resp = await client.put(
        "/rest/api/2/myself/password",
        json={"password": "newpassword", "currentPassword": "admin"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 204
