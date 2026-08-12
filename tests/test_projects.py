"""Tests for project listing and detail endpoints."""

import httpx

from tests.conftest import AUTH_HEADER


async def test_list_projects_returns_seeded(client: httpx.AsyncClient):
    """GET /rest/api/2/project should return all seeded projects."""
    resp = await client.get("/rest/api/2/project", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 5

    keys = {p["key"] for p in data}
    assert keys == {"RHAIRFE", "RHAISTRAT", "RHOAIENG", "AIPCC", "TEST"}

    # Each entry should have the expected structure
    for p in data:
        assert "id" in p
        assert "key" in p
        assert "name" in p
        assert "self" in p


async def test_get_project_rhoaieng(client: httpx.AsyncClient):
    """GET /rest/api/2/project/RHOAIENG should return the correct project details."""
    resp = await client.get("/rest/api/2/project/RHOAIENG", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert data["key"] == "RHOAIENG"
    assert data["name"] == "Red Hat OpenShift AI Engineering"

    # Should include issueTypes, components, and versions lists
    assert "issueTypes" in data
    assert isinstance(data["issueTypes"], list)

    # RHOAIENG is associated with Bug, Task, Story, Epic, Sub-task
    type_names = {it["name"] for it in data["issueTypes"]}
    assert "Bug" in type_names
    assert "Task" in type_names
    assert "Story" in type_names
    assert "Epic" in type_names
    assert "Sub-task" in type_names


async def test_get_project_not_found(client: httpx.AsyncClient):
    """GET /rest/api/2/project/NONEXIST should return 404."""
    resp = await client.get("/rest/api/2/project/NONEXIST", headers=AUTH_HEADER)
    assert resp.status_code == 404


async def test_create_project_version_v2_and_v3(client: httpx.AsyncClient):
    """Project versions can be seeded idempotently through both REST surfaces."""
    body = {"project": {"key": "RHAIRFE"}, "name": "rhoai-3.6.EA1"}
    v2 = await client.post("/rest/api/2/version", headers=AUTH_HEADER, json=body)
    assert v2.status_code == 201
    assert v2.json()["name"] == "rhoai-3.6.EA1"

    v3 = await client.post("/rest/api/3/version", headers=AUTH_HEADER, json=body)
    assert v3.status_code == 201
    assert v3.json()["id"] == v2.json()["id"]

    project = await client.get("/rest/api/2/project/RHAIRFE", headers=AUTH_HEADER)
    assert [version["name"] for version in project.json()["versions"]] == ["rhoai-3.6.EA1"]
