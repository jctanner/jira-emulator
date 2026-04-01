"""Tests for Personal Access Token (PAT) endpoints."""

import httpx
import pytest

from tests.conftest import AUTH_HEADER


async def test_create_token_returns_raw_token(client: httpx.AsyncClient):
    """POST /rest/pat/latest/tokens should create a token and return rawToken."""
    resp = await client.post(
        "/rest/pat/latest/tokens",
        json={"name": "Test Token"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201

    data = resp.json()
    assert "id" in data
    assert data["name"] == "Test Token"
    assert "rawToken" in data
    assert isinstance(data["rawToken"], str)
    assert len(data["rawToken"]) > 0
    assert "createdAt" in data


async def test_list_tokens_hides_raw_token(client: httpx.AsyncClient):
    """GET /rest/pat/latest/tokens should list tokens without rawToken."""
    # Create a token first
    create_resp = await client.post(
        "/rest/pat/latest/tokens",
        json={"name": "Listed Token"},
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201

    # List tokens
    resp = await client.get("/rest/pat/latest/tokens", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Find the token we created
    token = next((t for t in data if t["name"] == "Listed Token"), None)
    assert token is not None
    assert "id" in token
    assert "createdAt" in token
    # rawToken should NOT be present in the listing
    assert "rawToken" not in token


async def test_revoke_token(client: httpx.AsyncClient):
    """DELETE /rest/pat/latest/tokens/{id} should revoke the token (204)."""
    # Create a token
    create_resp = await client.post(
        "/rest/pat/latest/tokens",
        json={"name": "Revocable Token"},
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201
    token_id = create_resp.json()["id"]

    # Revoke it
    resp = await client.delete(
        f"/rest/pat/latest/tokens/{token_id}",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 204

    # After revoking, the token should no longer appear in the active list
    list_resp = await client.get("/rest/pat/latest/tokens", headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    active_ids = {t["id"] for t in list_resp.json()}
    assert token_id not in active_ids


async def test_revoke_nonexistent_token_returns_404(client: httpx.AsyncClient):
    """DELETE /rest/pat/latest/tokens/{id} for a missing token should return 404."""
    resp = await client.delete(
        "/rest/pat/latest/tokens/99999",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 404
