"""Tests for the read-only admin user directory."""

from datetime import datetime

import httpx
from sqlalchemy import select

from jira_emulator.database import get_session_factory
from jira_emulator.models.api_token import ApiToken
from jira_emulator.models.user import User
from jira_emulator.services.auth_service import verify_password


async def test_admin_page_lists_seeded_user_with_safe_credential_status(client: httpx.AsyncClient):
    response = await client.get("/admin/import")

    assert response.status_code == 200
    assert "User Management" in response.text
    assert "admin@example.com" in response.text
    assert "Admin User" in response.text
    assert "Password set" in response.text
    assert "Default Token" not in response.text
    assert "$2b$" not in response.text


async def test_admin_page_lists_inactive_users_and_counts_only_active_tokens(client: httpx.AsyncClient):
    password_hash = "sensitive-password-hash"
    active_token_hash = "sensitive-active-token-hash"
    revoked_token_hash = "sensitive-revoked-token-hash"

    factory = get_session_factory()
    async with factory() as db:
        user = User(
            username="disabled.user",
            display_name="Disabled User",
            email=None,
            password_hash=password_hash,
            active=False,
            created_at=datetime(2025, 1, 2, 3, 4),
        )
        db.add(user)
        await db.flush()
        db.add_all(
            [
                ApiToken(user_id=user.id, name="Active", token_hash=active_token_hash, active=True),
                ApiToken(user_id=user.id, name="Revoked", token_hash=revoked_token_hash, active=False),
            ]
        )
        await db.commit()

    response = await client.get("/admin/import")

    assert response.status_code == 200
    assert "disabled.user" in response.text
    assert "Disabled User" in response.text
    assert "Inactive" in response.text
    assert "2025-01-02 03:04 UTC" in response.text
    assert password_hash not in response.text
    assert active_token_hash not in response.text
    assert revoked_token_hash not in response.text

    row = response.text.split("disabled.user", 1)[1].split("</tr>", 1)[0]
    assert ">1</td>" in row


async def test_admin_page_reports_missing_password_and_sorts_usernames(client: httpx.AsyncClient):
    factory = get_session_factory()
    async with factory() as db:
        db.add_all(
            [
                User(username="zulu", display_name="Zulu", email="zulu@example.com", password_hash=None),
                User(username="Alpha", display_name="Alpha", email="alpha@example.com", password_hash=None),
            ]
        )
        await db.commit()

    response = await client.get("/admin/import")

    assert response.status_code == 200
    assert "No password" in response.text
    assert response.text.index(">admin</td>") < response.text.index(">Alpha</td>")
    assert response.text.index(">Alpha</td>") < response.text.index(">zulu</td>")


async def test_admin_can_create_and_edit_user(client: httpx.AsyncClient):
    create_response = await client.post(
        "/admin/users",
        data={
            "username": "managed.user",
            "display_name": "Managed User",
            "email": "MANAGED@EXAMPLE.COM",
            "password": "initial-secret",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 303
    assert "user_message=" in create_response.headers["location"]

    detail_response = await client.get("/admin/users/managed.user")
    assert detail_response.status_code == 200
    assert "Managed User" in detail_response.text
    assert "managed@example.com" in detail_response.text

    edit_response = await client.post(
        "/admin/users/managed.user/profile",
        data={"display_name": "Updated User", "email": "updated@example.com"},
        follow_redirects=False,
    )
    assert edit_response.status_code == 303

    duplicate_response = await client.post(
        "/admin/users",
        data={
            "username": "another",
            "display_name": "Another",
            "email": "UPDATED@example.com",
            "password": "secret",
        },
        follow_redirects=False,
    )
    assert duplicate_response.status_code == 303
    assert "user_error=" in duplicate_response.headers["location"]


async def test_admin_can_reset_password_and_deactivation_revokes_tokens(client: httpx.AsyncClient):
    await client.post(
        "/admin/users",
        data={
            "username": "lifecycle.user",
            "display_name": "Lifecycle User",
            "email": "lifecycle@example.com",
            "password": "old-secret",
        },
    )

    factory = get_session_factory()
    async with factory() as db:
        user = await db.scalar(select(User).where(User.username == "lifecycle.user"))
        token = ApiToken(
            user_id=user.id,
            name="Lifecycle Token",
            token_hash="private-token-hash",
            token_prefix="visible12",
            active=True,
        )
        db.add(token)
        await db.commit()
        token_id = token.id

    detail_response = await client.get("/admin/users/lifecycle.user")
    assert detail_response.status_code == 200
    assert "Lifecycle Token" in detail_response.text
    assert "visible12" in detail_response.text
    assert "private-token-hash" not in detail_response.text

    password_response = await client.post(
        "/admin/users/lifecycle.user/password",
        data={"password": "new-secret"},
        follow_redirects=False,
    )
    assert password_response.status_code == 303

    async with factory() as db:
        user = await db.scalar(select(User).where(User.username == "lifecycle.user"))
        assert verify_password("new-secret", user.password_hash)

    deactivate_response = await client.post(
        "/admin/users/lifecycle.user/status",
        data={"active": "false"},
        follow_redirects=False,
    )
    assert deactivate_response.status_code == 303

    async with factory() as db:
        user = await db.scalar(select(User).where(User.username == "lifecycle.user"))
        token = await db.get(ApiToken, token_id)
        assert user.active is False
        assert token.active is False


async def test_admin_can_revoke_token_and_cannot_deactivate_default_user(client: httpx.AsyncClient):
    factory = get_session_factory()
    async with factory() as db:
        admin = await db.scalar(select(User).where(User.username == "admin"))
        token = ApiToken(user_id=admin.id, name="Revoke Me", token_hash="secret-hash", active=True)
        db.add(token)
        await db.commit()
        token_id = token.id

    revoke_response = await client.post(
        f"/admin/users/admin/tokens/{token_id}/revoke",
        follow_redirects=False,
    )
    assert revoke_response.status_code == 303

    deactivate_response = await client.post(
        "/admin/users/admin/status",
        data={"active": "false"},
        follow_redirects=False,
    )
    assert deactivate_response.status_code == 303
    assert "error=" in deactivate_response.headers["location"]

    async with factory() as db:
        admin = await db.scalar(select(User).where(User.username == "admin"))
        token = await db.get(ApiToken, token_id)
        assert admin.active is True
        assert token.active is False
