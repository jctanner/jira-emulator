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


# ---------------------------------------------------------------------------
# ADF (Atlassian Document Format) – v2 vs v3
# ---------------------------------------------------------------------------

# A sample ADF document with bold, heading, and link nodes.
_SAMPLE_ADF = {
    "version": 1,
    "type": "doc",
    "content": [
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": "Problem Statement"}],
        },
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "This is "},
                {"type": "text", "text": "important", "marks": [{"type": "strong"}]},
                {"type": "text", "text": " because of "},
                {
                    "type": "text",
                    "text": "this link",
                    "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
                },
                {"type": "text", "text": "."},
            ],
        },
    ],
}


async def test_create_issue_with_adf_via_v3(client: httpx.AsyncClient):
    """Creating an issue via v3 with an ADF description should preserve it."""
    resp = await client.post(
        "/rest/api/3/issue",
        json={
            "fields": {
                "project": {"key": "RHOAIENG"},
                "summary": "ADF test issue",
                "issuetype": {"name": "Bug"},
                "description": _SAMPLE_ADF,
            }
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201, resp.text
    key = resp.json()["key"]

    # Read back via v3 → should get full ADF dict
    resp = await client.get(f"/rest/api/3/issue/{key}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    desc = resp.json()["fields"]["description"]
    assert isinstance(desc, dict)
    assert desc["type"] == "doc"
    assert desc == _SAMPLE_ADF

    # Read back via v2 → should get plain text
    resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    desc_v2 = resp.json()["fields"]["description"]
    assert isinstance(desc_v2, str)
    assert "Problem Statement" in desc_v2
    assert "important" in desc_v2
    assert "this link" in desc_v2


async def test_create_issue_plain_text_read_via_v3(client: httpx.AsyncClient):
    """Creating an issue via v2 with plain text, reading via v3 returns ADF."""
    resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "RHOAIENG"},
                "summary": "Plain text issue",
                "issuetype": {"name": "Bug"},
                "description": "Simple plain text description",
            }
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201, resp.text
    key = resp.json()["key"]

    # Read via v3 → wrapped in ADF paragraphs
    resp = await client.get(f"/rest/api/3/issue/{key}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    desc = resp.json()["fields"]["description"]
    assert isinstance(desc, dict)
    assert desc["type"] == "doc"
    assert desc["version"] == 1
    assert desc["content"][0]["content"][0]["text"] == "Simple plain text description"

    # Read via v2 → still plain text
    resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["fields"]["description"] == "Simple plain text description"


async def test_comment_adf_via_v3(client: httpx.AsyncClient):
    """Adding a comment via v3 with ADF body should preserve it."""
    created = await _create_issue(client)
    key = created["key"]

    adf_body = {
        "version": 1,
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "ADF comment"}]},
        ],
    }

    # Add comment via v3
    resp = await client.post(
        f"/rest/api/3/issue/{key}/comment",
        json={"body": adf_body},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["body"]
    assert isinstance(body, dict)
    assert body["type"] == "doc"

    # Read comments via v2 → plain text
    resp = await client.get(
        f"/rest/api/2/issue/{key}/comment",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    v2_body = resp.json()["comments"][0]["body"]
    assert isinstance(v2_body, str)
    assert v2_body == "ADF comment"
