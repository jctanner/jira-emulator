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


# ---------------------------------------------------------------------------
# v3 search endpoints — nextPageToken cursor pagination
# ---------------------------------------------------------------------------


async def test_v3_search_post_returns_cursor_pagination(client: httpx.AsyncClient):
    """POST /rest/api/3/search returns nextPageToken/isLast instead of startAt."""
    await _create_issues(client, count=3)

    resp = await client.post(
        "/rest/api/3/search",
        json={"jql": "project = RHOAIENG", "maxResults": 2},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 3
    assert data["isLast"] is False
    assert "nextPageToken" in data
    # v3 should NOT have startAt
    assert "startAt" not in data
    assert len(data["issues"]) == 2


async def test_v3_search_post_last_page(client: httpx.AsyncClient):
    """POST /rest/api/3/search last page has isLast=True and no nextPageToken."""
    await _create_issues(client, count=2)

    resp = await client.post(
        "/rest/api/3/search",
        json={"jql": "project = RHOAIENG", "maxResults": 50},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 2
    assert data["isLast"] is True
    assert "nextPageToken" not in data


async def test_v3_search_post_walk_all_pages(client: httpx.AsyncClient):
    """Walk all pages using nextPageToken via POST /rest/api/3/search."""
    await _create_issues(client, count=5)

    all_keys: set[str] = set()
    token = None

    for _ in range(10):  # safety limit
        body: dict = {"jql": "project = RHOAIENG", "maxResults": 2}
        if token:
            body["nextPageToken"] = token

        resp = await client.post(
            "/rest/api/3/search",
            json=body,
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200
        data = resp.json()

        for issue in data["issues"]:
            all_keys.add(issue["key"])

        if data["isLast"]:
            assert "nextPageToken" not in data
            break
        token = data["nextPageToken"]

    assert len(all_keys) == 5


async def test_v3_search_jql_post(client: httpx.AsyncClient):
    """POST /rest/api/3/search/jql works with cursor pagination."""
    await _create_issues(client, count=3)

    resp = await client.post(
        "/rest/api/3/search/jql",
        json={"jql": "project = RHOAIENG", "maxResults": 2},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 3
    assert data["isLast"] is False
    assert "nextPageToken" in data
    assert "startAt" not in data
    assert len(data["issues"]) == 2

    # Use token for next page
    resp2 = await client.post(
        "/rest/api/3/search/jql",
        json={
            "jql": "project = RHOAIENG",
            "maxResults": 2,
            "nextPageToken": data["nextPageToken"],
        },
        headers=AUTH_HEADER,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["isLast"] is True
    assert len(data2["issues"]) == 1


async def test_v3_search_jql_get(client: httpx.AsyncClient):
    """GET /rest/api/3/search/jql works with nextPageToken query param."""
    await _create_issues(client, count=3)

    resp = await client.get(
        "/rest/api/3/search/jql",
        params={"jql": "project = RHOAIENG", "maxResults": "2"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] == 3
    assert data["isLast"] is False
    assert "nextPageToken" in data
    assert "startAt" not in data

    # Follow the token
    resp2 = await client.get(
        "/rest/api/3/search/jql",
        params={
            "jql": "project = RHOAIENG",
            "maxResults": "2",
            "nextPageToken": data["nextPageToken"],
        },
        headers=AUTH_HEADER,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["isLast"] is True
    assert len(data2["issues"]) == 1


async def test_v2_search_unaffected_by_v3_changes(client: httpx.AsyncClient):
    """v2 endpoints still return startAt/maxResults, never nextPageToken."""
    await _create_issues(client, count=3)

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": "project = RHOAIENG", "maxResults": 2},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    data = resp.json()
    assert "startAt" in data
    assert "maxResults" in data
    assert "nextPageToken" not in data
    assert "isLast" not in data


# ---------------------------------------------------------------------------
# ORDER BY key: numeric within a project, as in Jira
# ---------------------------------------------------------------------------


def _expected_key_order(created: list[dict], reverse: bool = False) -> list[str]:
    keys = [c["key"] for c in created]
    return sorted(keys, key=lambda k: int(k.split("-")[1]), reverse=reverse)


@pytest.mark.parametrize("api", ["2", "3"])
@pytest.mark.parametrize("direction", ["ASC", "DESC"])
async def test_order_by_key_is_numeric(client: httpx.AsyncClient, api: str, direction: str):
    """RHOAIENG-2 sorts before RHOAIENG-10 (a string sort puts -10 first)."""
    created = await _create_issues(client, count=11)
    jql = f"project = RHOAIENG ORDER BY key {direction}"
    path = "search" if api == "2" else "search/jql"

    resp = await client.post(
        f"/rest/api/{api}/{path}", json={"jql": jql, "maxResults": 50, "fields": ["key"]}, headers=AUTH_HEADER
    )

    assert resp.status_code == 200
    keys = [i["key"] for i in resp.json()["issues"]]
    assert keys == _expected_key_order(created, reverse=direction == "DESC")


async def test_default_order_is_numeric_key(client: httpx.AsyncClient):
    created = await _create_issues(client, count=11)

    resp = await client.get(
        "/rest/api/2/search", params={"jql": "project = RHOAIENG", "maxResults": 50}, headers=AUTH_HEADER
    )

    assert resp.status_code == 200
    assert [i["key"] for i in resp.json()["issues"]] == _expected_key_order(created)


async def test_order_by_key_groups_projects(client: httpx.AsyncClient):
    """Keys sort by project first, then by number."""
    created = await _create_issues(client, count=2)
    other = await client.post(
        "/rest/api/2/issue",
        json={"fields": {"project": {"key": "RHAIRFE"}, "summary": "rfe", "issuetype": {"name": "Feature Request"}}},
        headers=AUTH_HEADER,
    )
    assert other.status_code == 201, other.text

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": "project in (RHOAIENG, RHAIRFE) ORDER BY issuekey ASC", "fields": ["key"]},
        headers=AUTH_HEADER,
    )

    keys = [i["key"] for i in resp.json()["issues"]]
    assert keys == [other.json()["key"]] + _expected_key_order(created)
