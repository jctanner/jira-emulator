"""Jira's own page URLs: /browse/KEY-123, /browse/KEY, /projects/KEY."""

import httpx

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


async def _create_issue(client, summary="Browse me"):
    body = {"fields": {"project": {"key": "RHOAIENG"}, "summary": summary, "issuetype": {"name": "Bug"}}}
    resp = await client.post("/rest/api/2/issue", json=body, headers=AUTH)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["key"]


async def test_browse_serves_the_issue_page(client: httpx.AsyncClient):
    key = await _create_issue(client, "Browse me")
    resp = await client.get(f"/browse/{key}")
    assert resp.status_code == 200
    assert "Browse me" in resp.text
    assert resp.text == (await client.get(f"/issue/{key}")).text


async def test_browse_serves_the_project_page_for_a_project_key(client: httpx.AsyncClient):
    resp = await client.get("/browse/RHOAIENG")
    assert resp.status_code == 200
    assert resp.text == (await client.get("/project/RHOAIENG")).text


async def test_projects_is_jira_clouds_project_url(client: httpx.AsyncClient):
    resp = await client.get("/projects/RHOAIENG")
    assert resp.status_code == 200
    assert resp.text == (await client.get("/project/RHOAIENG")).text


async def test_browse_of_an_unknown_issue_is_not_found(client: httpx.AsyncClient):
    resp = await client.get("/browse/RHOAIENG-999999")
    assert resp.status_code == 404
