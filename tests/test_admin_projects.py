"""Tests for admin project maintenance."""

import httpx

from tests.conftest import AUTH_HEADER


async def test_admin_api_create_project(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/admin/projects",
        json={
            "key": "admnew",
            "name": "Admin New Project",
            "description": "Created by admin API",
            "lead": "admin",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201

    data = resp.json()
    assert data["key"] == "ADMNEW"
    assert data["name"] == "Admin New Project"
    assert data["description"] == "Created by admin API"
    assert data["lead"] == "admin"

    project_resp = await client.get("/rest/api/2/project/ADMNEW", headers=AUTH_HEADER)
    assert project_resp.status_code == 200
    project_data = project_resp.json()
    assert project_data["key"] == "ADMNEW"
    assert project_data["issueTypes"]


async def test_admin_api_rejects_duplicate_project(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/admin/projects",
        json={"key": "TEST", "name": "Duplicate Test"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


async def test_admin_api_delete_project_removes_issues(client: httpx.AsyncClient):
    create_resp = await client.post(
        "/api/admin/projects",
        json={"key": "DELME", "name": "Delete Me"},
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201

    issue_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "DELME"},
                "issuetype": {"name": "Bug"},
                "summary": "Issue to delete with project",
            }
        },
        headers=AUTH_HEADER,
    )
    assert issue_resp.status_code == 201
    issue_key = issue_resp.json()["key"]

    delete_resp = await client.delete("/api/admin/projects/DELME", headers=AUTH_HEADER)
    assert delete_resp.status_code == 204

    project_resp = await client.get("/rest/api/2/project/DELME", headers=AUTH_HEADER)
    assert project_resp.status_code == 404
    deleted_issue_resp = await client.get(f"/rest/api/2/issue/{issue_key}", headers=AUTH_HEADER)
    assert deleted_issue_resp.status_code == 404


async def test_admin_web_project_maintenance_create_and_delete(client: httpx.AsyncClient):
    page_resp = await client.get("/admin/import")
    assert page_resp.status_code == 200
    assert "Project Maintenance" in page_resp.text
    assert 'action="/admin/projects"' in page_resp.text

    create_resp = await client.post(
        "/admin/projects",
        data={"key": "WEBNEW", "name": "Web New Project"},
        follow_redirects=False,
    )
    assert create_resp.status_code == 303
    assert create_resp.headers["location"].startswith("/admin/import?project_message=")

    project_resp = await client.get("/rest/api/2/project/WEBNEW", headers=AUTH_HEADER)
    assert project_resp.status_code == 200

    delete_resp = await client.post(
        "/admin/projects/WEBNEW/delete",
        follow_redirects=False,
    )
    assert delete_resp.status_code == 303

    deleted_resp = await client.get("/rest/api/2/project/WEBNEW", headers=AUTH_HEADER)
    assert deleted_resp.status_code == 404
