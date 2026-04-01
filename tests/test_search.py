"""Tests for JQL search endpoints (POST and GET)."""

import httpx
import pytest

from tests.conftest import AUTH_HEADER


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _create_issues(client: httpx.AsyncClient, count: int = 3) -> list[dict]:
    """Create *count* issues in RHOAIENG and return their creation responses."""
    results = []
    for i in range(1, count + 1):
        resp = await client.post(
            "/rest/api/2/issue",
            json={
                "fields": {
                    "project": {"key": "RHOAIENG"},
                    "summary": f"Search test issue {i}",
                    "issuetype": {"name": "Bug"},
                }
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 201
        results.append(resp.json())
    return results


# ---------------------------------------------------------------------------
# POST /rest/api/2/search
# ---------------------------------------------------------------------------


async def test_search_post_by_project(client: httpx.AsyncClient):
    """POST /rest/api/2/search with JQL 'project = RHOAIENG' finds created issues."""
    created = await _create_issues(client, count=3)

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": "project = RHOAIENG", "maxResults": 50},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 3
    assert len(data["issues"]) == 3

    returned_keys = {issue["key"] for issue in data["issues"]}
    for c in created:
        assert c["key"] in returned_keys


async def test_search_post_pagination(client: httpx.AsyncClient):
    """POST /rest/api/2/search with startAt/maxResults paginates correctly."""
    await _create_issues(client, count=5)

    # First page: 2 results
    resp1 = await client.post(
        "/rest/api/2/search",
        json={"jql": "project = RHOAIENG", "startAt": 0, "maxResults": 2},
        headers=AUTH_HEADER,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["total"] == 5
    assert data1["startAt"] == 0
    assert data1["maxResults"] == 2
    assert len(data1["issues"]) == 2

    # Second page: next 2 results
    resp2 = await client.post(
        "/rest/api/2/search",
        json={"jql": "project = RHOAIENG", "startAt": 2, "maxResults": 2},
        headers=AUTH_HEADER,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["total"] == 5
    assert data2["startAt"] == 2
    assert len(data2["issues"]) == 2

    # The two pages should return different issues
    page1_keys = {i["key"] for i in data1["issues"]}
    page2_keys = {i["key"] for i in data2["issues"]}
    assert page1_keys.isdisjoint(page2_keys)


async def test_search_post_empty_result(client: httpx.AsyncClient):
    """POST /rest/api/2/search for a project with no issues returns total 0."""
    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": "project = RHOAIENG", "maxResults": 10},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 0
    assert data["issues"] == []


# ---------------------------------------------------------------------------
# GET /rest/api/2/search?jql=...
# ---------------------------------------------------------------------------


async def test_search_get_by_jql(client: httpx.AsyncClient):
    """GET /rest/api/2/search?jql=... should also work and return results."""
    await _create_issues(client, count=2)

    resp = await client.get(
        "/rest/api/2/search",
        params={"jql": "project = RHOAIENG", "maxResults": "50"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 2
    assert len(data["issues"]) == 2


async def test_search_get_pagination(client: httpx.AsyncClient):
    """GET /rest/api/2/search with startAt/maxResults via query params."""
    await _create_issues(client, count=4)

    resp = await client.get(
        "/rest/api/2/search",
        params={"jql": "project = RHOAIENG", "startAt": "1", "maxResults": "2"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 4
    assert data["startAt"] == 1
    assert data["maxResults"] == 2
    assert len(data["issues"]) == 2
