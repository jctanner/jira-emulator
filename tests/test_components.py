"""Tests for Jira project component endpoints."""

import httpx

from tests.conftest import AUTH_HEADER


async def _create_component(
    client: httpx.AsyncClient,
    name: str = "AI Core Platform",
    project: str = "TEST",
    description: str = "Platform component",
) -> dict:
    resp = await client.post(
        "/rest/api/2/component",
        json={"name": name, "project": project, "description": description, "leadUserName": "component-lead"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_project_components_endpoint_returns_created_component(client: httpx.AsyncClient):
    component = await _create_component(client, name="Runtime")

    resp = await client.get("/rest/api/2/project/TEST/components", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()

    assert [item["name"] for item in data] == ["Runtime"]
    assert data[0]["id"] == component["id"]
    assert data[0]["project"] == "TEST"
    assert data[0]["projectId"] == component["projectId"]
    assert data[0]["assigneeType"] == "PROJECT_DEFAULT"
    assert data[0]["isAssigneeTypeValid"] is True

    project_resp = await client.get("/rest/api/2/project/TEST", headers=AUTH_HEADER)
    project_components = project_resp.json()["components"]
    assert any(item["name"] == "Runtime" and item["project"] == "TEST" for item in project_components)


async def test_v3_project_components_endpoint_uses_rewrite(client: httpx.AsyncClient):
    await _create_component(client, name="V3 Runtime")

    resp = await client.get("/rest/api/3/project/TEST/components", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert [item["name"] for item in resp.json()] == ["V3 Runtime"]


async def test_project_components_unknown_project_returns_404(client: httpx.AsyncClient):
    resp = await client.get("/rest/api/2/project/NOPE/components", headers=AUTH_HEADER)
    assert resp.status_code == 404


async def test_create_component_validates_duplicates_and_project_scope(client: httpx.AsyncClient):
    await _create_component(client, name="Shared")

    duplicate_resp = await client.post(
        "/rest/api/2/component",
        json={"name": "Shared", "project": "TEST"},
        headers=AUTH_HEADER,
    )
    assert duplicate_resp.status_code == 400

    other_project_resp = await client.post(
        "/rest/api/2/component",
        json={"name": "Shared", "project": "RHOAIENG"},
        headers=AUTH_HEADER,
    )
    assert other_project_resp.status_code == 201
    assert other_project_resp.json()["project"] == "RHOAIENG"


async def test_create_component_requires_name_and_project(client: httpx.AsyncClient):
    missing_name = await client.post("/rest/api/2/component", json={"project": "TEST"}, headers=AUTH_HEADER)
    assert missing_name.status_code == 400

    missing_project = await client.post("/rest/api/2/component", json={"name": "Runtime"}, headers=AUTH_HEADER)
    assert missing_project.status_code == 400


async def test_get_and_update_component(client: httpx.AsyncClient):
    component = await _create_component(client, name="Old Name")

    get_resp = await client.get(f"/rest/api/2/component/{component['id']}", headers=AUTH_HEADER)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Old Name"

    update_resp = await client.put(
        f"/rest/api/2/component/{component['id']}",
        json={"name": "New Name", "description": "Updated"},
        headers=AUTH_HEADER,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "New Name"
    assert update_resp.json()["description"] == "Updated"


async def test_component_rename_is_reflected_in_issue_response(client: httpx.AsyncClient):
    issue_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "TEST"},
                "summary": "Component rename issue",
                "issuetype": {"name": "Task"},
                "components": [{"name": "Before Rename"}],
            }
        },
        headers=AUTH_HEADER,
    )
    assert issue_resp.status_code == 201
    key = issue_resp.json()["key"]

    components_resp = await client.get("/rest/api/2/project/TEST/components", headers=AUTH_HEADER)
    component_id = next(item["id"] for item in components_resp.json() if item["name"] == "Before Rename")

    rename_resp = await client.put(
        f"/rest/api/2/component/{component_id}",
        json={"name": "After Rename"},
        headers=AUTH_HEADER,
    )
    assert rename_resp.status_code == 200

    get_issue_resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH_HEADER)
    assert [item["name"] for item in get_issue_resp.json()["fields"]["components"]] == ["After Rename"]


async def test_update_component_rejects_duplicates_and_project_moves(client: httpx.AsyncClient):
    first = await _create_component(client, name="First")
    second = await _create_component(client, name="Second")

    duplicate_resp = await client.put(
        f"/rest/api/2/component/{second['id']}",
        json={"name": "First"},
        headers=AUTH_HEADER,
    )
    assert duplicate_resp.status_code == 400

    move_resp = await client.put(
        f"/rest/api/2/component/{first['id']}",
        json={"project": "RHOAIENG"},
        headers=AUTH_HEADER,
    )
    assert move_resp.status_code == 400


async def test_paginated_project_components_supports_query_and_ordering(client: httpx.AsyncClient):
    await _create_component(client, name="Beta")
    await _create_component(client, name="Alpha")
    await _create_component(client, name="Gamma")

    resp = await client.get(
        "/rest/api/2/project/TEST/component?query=a&orderBy=-name&startAt=0&maxResults=2",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["isLast"] is False
    assert [item["name"] for item in data["values"]] == ["Gamma", "Beta"]
    assert all("issueCount" in item for item in data["values"])


async def test_global_components_supports_project_filter(client: httpx.AsyncClient):
    await _create_component(client, name="Only Test", project="TEST")
    await _create_component(client, name="Only Engineering", project="RHOAIENG")

    resp = await client.get("/rest/api/2/component?projectIdsOrKeys=RHOAIENG", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["values"][0]["name"] == "Only Engineering"
    assert data["values"][0]["project"] == "RHOAIENG"


async def test_related_issue_counts_and_delete_component(client: httpx.AsyncClient):
    issue_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "TEST"},
                "summary": "Delete component issue",
                "issuetype": {"name": "Task"},
                "components": [{"name": "Temporary"}],
            }
        },
        headers=AUTH_HEADER,
    )
    assert issue_resp.status_code == 201
    key = issue_resp.json()["key"]

    components = (await client.get("/rest/api/2/project/TEST/components", headers=AUTH_HEADER)).json()
    component_id = next(item["id"] for item in components if item["name"] == "Temporary")

    count_resp = await client.get(f"/rest/api/2/component/{component_id}/relatedIssueCounts", headers=AUTH_HEADER)
    assert count_resp.status_code == 200
    assert count_resp.json()["issueCount"] == 1

    delete_resp = await client.delete(f"/rest/api/2/component/{component_id}", headers=AUTH_HEADER)
    assert delete_resp.status_code == 204

    issue_after_delete = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH_HEADER)
    assert issue_after_delete.json()["fields"]["components"] == []


async def test_delete_component_can_move_issue_associations(client: httpx.AsyncClient):
    source = await _create_component(client, name="Source")
    target = await _create_component(client, name="Target")
    issue_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "TEST"},
                "summary": "Move component issue",
                "issuetype": {"name": "Task"},
                "components": [{"name": "Source"}],
            }
        },
        headers=AUTH_HEADER,
    )
    assert issue_resp.status_code == 201

    delete_resp = await client.delete(
        f"/rest/api/2/component/{source['id']}?moveIssuesTo={target['id']}",
        headers=AUTH_HEADER,
    )
    assert delete_resp.status_code == 204

    issue_after_delete = await client.get(f"/rest/api/2/issue/{issue_resp.json()['key']}", headers=AUTH_HEADER)
    assert [item["name"] for item in issue_after_delete.json()["fields"]["components"]] == ["Target"]


async def test_issue_create_deduplicates_repeated_component_names(client: httpx.AsyncClient):
    resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "TEST"},
                "summary": "Repeated components",
                "issuetype": {"name": "Task"},
                "components": [{"name": "Runtime"}, {"name": "Runtime"}],
            }
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201

    issue_resp = await client.get(f"/rest/api/2/issue/{resp.json()['key']}", headers=AUTH_HEADER)
    assert [item["name"] for item in issue_resp.json()["fields"]["components"]] == ["Runtime"]


async def test_issue_update_deduplicates_repeated_component_names(client: httpx.AsyncClient):
    issue_resp = await client.post(
        "/rest/api/2/issue",
        json={"fields": {"project": {"key": "TEST"}, "summary": "Update repeated", "issuetype": {"name": "Task"}}},
        headers=AUTH_HEADER,
    )
    assert issue_resp.status_code == 201
    key = issue_resp.json()["key"]

    replace_resp = await client.put(
        f"/rest/api/2/issue/{key}",
        json={"fields": {"components": [{"name": "Runtime"}, {"name": "Runtime"}]}},
        headers=AUTH_HEADER,
    )
    assert replace_resp.status_code == 204

    add_resp = await client.put(
        f"/rest/api/2/issue/{key}",
        json={"update": {"components": [{"add": {"name": "Runtime"}}, {"add": {"name": "Runtime"}}]}},
        headers=AUTH_HEADER,
    )
    assert add_resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH_HEADER)
    assert [item["name"] for item in get_resp.json()["fields"]["components"]] == ["Runtime"]


async def test_import_creates_components_and_deduplicates_repeated_names(client: httpx.AsyncClient):
    issue = {
        "key": "COMPI-1",
        "summary": "Imported components",
        "status": "New",
        "priority": "Major",
        "issue_type": "Bug",
        "reporter": "Test User",
        "project": {"key": "COMPI", "name": "Component Import Project"},
        "components": [{"name": "Runtime"}, {"name": "Runtime"}, "Docs"],
        "labels": [],
        "affects_versions": [],
        "fix_versions": [],
    }

    first_resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH_HEADER)
    assert first_resp.status_code == 200
    second_resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH_HEADER)
    assert second_resp.status_code == 200

    issue_resp = await client.get("/rest/api/2/issue/COMPI-1", headers=AUTH_HEADER)
    assert sorted(item["name"] for item in issue_resp.json()["fields"]["components"]) == ["Docs", "Runtime"]

    components_resp = await client.get("/rest/api/2/project/COMPI/components", headers=AUTH_HEADER)
    assert sorted(item["name"] for item in components_resp.json()) == ["Docs", "Runtime"]
