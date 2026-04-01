"""Tests for project listing and detail endpoints."""

import httpx
import pytest

from tests.conftest import AUTH_HEADER


async def test_list_projects_returns_four(client: httpx.AsyncClient):
    """GET /rest/api/2/project should return exactly 4 seeded projects."""
    resp = await client.get("/rest/api/2/project", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 4

    keys = {p["key"] for p in data}
    assert keys == {"RHAIRFE", "RHAISTRAT", "RHOAIENG", "AIPCC"}

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
