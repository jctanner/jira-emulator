"""Integration smoke tests for REST API v3."""

import httpx
import pytest


@pytest.mark.asyncio
async def test_v3_priority_endpoint(client: httpx.AsyncClient, auth_header: dict):
    resp = await client.get("/rest/api/3/priority", headers=auth_header)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_v3_issue_returns_adf_description(client: httpx.AsyncClient, auth_header: dict):
    create_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "TEST"},
                "summary": "V3 ADF test",
                "issuetype": {"name": "Bug"},
                "description": "Plain text for v3 test",
            }
        },
        headers=auth_header,
    )
    assert create_resp.status_code == 201
    key = create_resp.json()["key"]

    resp = await client.get(f"/rest/api/3/issue/{key}", headers=auth_header)
    assert resp.status_code == 200
    desc = resp.json()["fields"]["description"]
    assert isinstance(desc, dict)
    assert desc["type"] == "doc"


@pytest.mark.asyncio
async def test_v3_search_cursor_pagination(client: httpx.AsyncClient, auth_header: dict):
    resp = await client.post(
        "/rest/api/3/search",
        json={"jql": "project = TEST", "maxResults": 5},
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "isLast" in data
