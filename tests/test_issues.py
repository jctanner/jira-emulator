"""Tests for issue CRUD, transitions, and comments."""

import httpx
import pytest

from tests.conftest import AUTH_HEADER


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _create_issue(
    client: httpx.AsyncClient,
    project_key: str = "RHOAIENG",
    summary: str = "Test issue",
    issue_type: str = "Bug",
) -> dict:
    """Create an issue and return the JSON response body."""
    resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Issue CRUD
# ---------------------------------------------------------------------------


async def test_create_issue(client: httpx.AsyncClient):
    """POST /rest/api/2/issue should create an issue with key RHOAIENG-1."""
    data = await _create_issue(client)

    assert data["key"] == "RHOAIENG-1"
    assert "id" in data
    assert "self" in data


async def test_get_issue(client: httpx.AsyncClient):
    """GET /rest/api/2/issue/{key} should return full issue details."""
    created = await _create_issue(client, summary="Get me")

    resp = await client.get(
        f"/rest/api/2/issue/{created['key']}",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["key"] == created["key"]
    assert "fields" in data
    assert data["fields"]["summary"] == "Get me"
    assert "status" in data["fields"]
    assert "issuetype" in data["fields"]
    assert "project" in data["fields"]


async def test_get_issue_not_found(client: httpx.AsyncClient):
    """GET /rest/api/2/issue/NONEXIST-999 should return 404."""
    resp = await client.get(
        "/rest/api/2/issue/NONEXIST-999",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 404


async def test_update_issue_summary(client: httpx.AsyncClient):
    """PUT /rest/api/2/issue/{key} should update the summary and return 204."""
    created = await _create_issue(client, summary="Original title")

    resp = await client.put(
        f"/rest/api/2/issue/{created['key']}",
        json={"fields": {"summary": "Updated title"}},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 204

    # Verify the update took effect
    get_resp = await client.get(
        f"/rest/api/2/issue/{created['key']}",
        headers=AUTH_HEADER,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["fields"]["summary"] == "Updated title"


async def test_delete_issue(client: httpx.AsyncClient):
    """DELETE /rest/api/2/issue/{key} should delete the issue (204)."""
    created = await _create_issue(client, summary="Delete me")

    resp = await client.delete(
        f"/rest/api/2/issue/{created['key']}",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 204

    # Verify the issue is gone
    get_resp = await client.get(
        f"/rest/api/2/issue/{created['key']}",
        headers=AUTH_HEADER,
    )
    assert get_resp.status_code == 404


async def test_delete_nonexistent_issue(client: httpx.AsyncClient):
    """DELETE /rest/api/2/issue/FAKE-1 should return 404."""
    resp = await client.delete(
        "/rest/api/2/issue/FAKE-1",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


async def test_get_transitions(client: httpx.AsyncClient):
    """GET /rest/api/2/issue/{key}/transitions should return available transitions."""
    created = await _create_issue(client)

    resp = await client.get(
        f"/rest/api/2/issue/{created['key']}/transitions",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert "transitions" in data
    assert isinstance(data["transitions"], list)
    assert len(data["transitions"]) > 0

    # Each transition should have id, name, and a to dict
    for t in data["transitions"]:
        assert "id" in t
        assert "name" in t
        assert "to" in t
        assert "name" in t["to"]


async def test_perform_transition(client: httpx.AsyncClient):
    """POST /rest/api/2/issue/{key}/transitions should change the issue status."""
    created = await _create_issue(client)

    # Fetch available transitions
    trans_resp = await client.get(
        f"/rest/api/2/issue/{created['key']}/transitions",
        headers=AUTH_HEADER,
    )
    transitions = trans_resp.json()["transitions"]
    assert len(transitions) > 0

    target_transition = transitions[0]

    # Perform the transition
    resp = await client.post(
        f"/rest/api/2/issue/{created['key']}/transitions",
        json={"transition": {"id": target_transition["id"]}},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 204

    # Verify the status changed
    get_resp = await client.get(
        f"/rest/api/2/issue/{created['key']}",
        headers=AUTH_HEADER,
    )
    assert get_resp.status_code == 200
    new_status = get_resp.json()["fields"]["status"]["name"]
    assert new_status == target_transition["to"]["name"]


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


async def test_add_comment(client: httpx.AsyncClient):
    """POST /rest/api/2/issue/{key}/comment should add a comment (201)."""
    created = await _create_issue(client)

    resp = await client.post(
        f"/rest/api/2/issue/{created['key']}/comment",
        json={"body": "This is a test comment."},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201

    data = resp.json()
    assert data["body"] == "This is a test comment."
    assert "id" in data
    assert "author" in data
    assert "created" in data


async def test_list_comments(client: httpx.AsyncClient):
    """GET /rest/api/2/issue/{key}/comment should list all comments."""
    created = await _create_issue(client)

    # Add two comments
    await client.post(
        f"/rest/api/2/issue/{created['key']}/comment",
        json={"body": "First comment"},
        headers=AUTH_HEADER,
    )
    await client.post(
        f"/rest/api/2/issue/{created['key']}/comment",
        json={"body": "Second comment"},
        headers=AUTH_HEADER,
    )

    resp = await client.get(
        f"/rest/api/2/issue/{created['key']}/comment",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 2
    assert len(data["comments"]) == 2
    assert data["comments"][0]["body"] == "First comment"
    assert data["comments"][1]["body"] == "Second comment"
