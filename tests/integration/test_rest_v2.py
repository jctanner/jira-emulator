"""Integration smoke tests for REST API v2."""

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_check(client: httpx.AsyncClient, auth_header: dict):
    resp = await client.get("/rest/api/2/priority", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "name" in data[0]


@pytest.mark.asyncio
async def test_seed_projects_exist(client: httpx.AsyncClient, auth_header: dict):
    resp = await client.get("/rest/api/2/project", headers=auth_header)
    assert resp.status_code == 200
    keys = {p["key"] for p in resp.json()}
    assert {"RHOAIENG", "RHAIRFE", "RHAISTRAT", "TEST"} <= keys


@pytest.mark.asyncio
async def test_create_and_get_issue(client: httpx.AsyncClient, auth_header: dict):
    create_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "TEST"},
                "summary": "Integration test issue",
                "issuetype": {"name": "Bug"},
            }
        },
        headers=auth_header,
    )
    assert create_resp.status_code == 201
    key = create_resp.json()["key"]
    assert key.startswith("TEST-")

    get_resp = await client.get(f"/rest/api/2/issue/{key}", headers=auth_header)
    assert get_resp.status_code == 200
    assert get_resp.json()["fields"]["summary"] == "Integration test issue"


@pytest.mark.asyncio
async def test_jql_search(client: httpx.AsyncClient, auth_header: dict):
    await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "TEST"},
                "summary": "Searchable issue",
                "issuetype": {"name": "Task"},
            }
        },
        headers=auth_header,
    )

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": "project = TEST", "maxResults": 10},
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_auth_header_accepted(client: httpx.AsyncClient, auth_header: dict):
    """Verify that requests with valid auth succeed."""
    resp = await client.get("/rest/api/2/priority", headers=auth_header)
    assert resp.status_code == 200
