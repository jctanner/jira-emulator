"""Integration tests for v1.0 project configuration import."""

import json

import httpx
import pytest

MINIMAL_CONFIG = {
    "version": "1.0",
    "metadata": {
        "exported_at": "2026-05-01T00:00:00+00:00",
        "source": "https://example.atlassian.net",
        "project": "INTCFG",
    },
    "statuses": [
        {"status_id": "1", "name": "Open", "status_category": "new"},
        {"status_id": "2", "name": "In Progress", "status_category": "indeterminate"},
        {"status_id": "3", "name": "Done", "status_category": "done"},
    ],
    "issue_types": [
        {"name": "Bug", "subtask": False, "description": "A bug"},
        {"name": "Task", "subtask": False, "description": "A task"},
    ],
    "priorities": [
        {"name": "Critical", "sort_order": 1},
        {"name": "Normal", "sort_order": 2},
    ],
    "resolutions": [
        {"name": "Fixed"},
        {"name": "Won't Do"},
    ],
    "link_types": [
        {
            "name": "Blocks",
            "inward_description": "is blocked by",
            "outward_description": "blocks",
        },
    ],
    "custom_fields": [
        {
            "field_id": "customfield_99901",
            "name": "Test Field",
            "field_type": "string",
            "description": "A test custom field",
        },
    ],
    "workflows": [
        {
            "workflow_id": "wf1",
            "name": "INTCFG Workflow",
            "statuses": [
                {"status_id": "1", "sequence": 1},
                {"status_id": "2", "sequence": 2},
                {"status_id": "3", "sequence": 3},
            ],
        },
    ],
    "project": {
        "key": "INTCFG",
        "name": "Integration Config Test",
        "description": "Project for integration config import tests",
        "issue_types": ["Bug", "Task"],
        "workflows": [
            {"issue_type": "Bug", "workflow_id": "wf1"},
            {"issue_type": "Task", "workflow_id": "wf1"},
        ],
    },
}


async def _import_config(client: httpx.AsyncClient, auth_header: dict, config: dict | None = None):
    """Upload a config JSON to the import endpoint and return the response."""
    payload = json.dumps(config or MINIMAL_CONFIG).encode()
    return await client.post(
        "/api/admin/import/project-config",
        headers=auth_header,
        files={"file": ("config.json", payload, "application/json")},
    )


@pytest.mark.asyncio
async def test_config_import_creates_project(client: httpx.AsyncClient, auth_header: dict):
    """Config import creates a project visible via the REST API."""
    resp = await _import_config(client, auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["projects"] == 1
    assert data["errors"] == []

    proj_resp = await client.get("/rest/api/2/project/INTCFG", headers=auth_header)
    assert proj_resp.status_code == 200
    assert proj_resp.json()["name"] == "Integration Config Test"


@pytest.mark.asyncio
async def test_config_import_statuses_visible(client: httpx.AsyncClient, auth_header: dict):
    """Imported statuses are returned by GET /rest/api/2/status."""
    await _import_config(client, auth_header)

    resp = await client.get("/rest/api/2/status", headers=auth_header)
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()}
    assert {"Open", "In Progress", "Done"} <= names


@pytest.mark.asyncio
async def test_config_import_enables_issue_creation(client: httpx.AsyncClient, auth_header: dict):
    """After config import, issues can be created in the imported project."""
    await _import_config(client, auth_header)

    create_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "INTCFG"},
                "summary": "Issue in imported project",
                "issuetype": {"name": "Bug"},
            },
        },
        headers=auth_header,
    )
    assert create_resp.status_code == 201
    key = create_resp.json()["key"]
    assert key == "INTCFG-1"

    get_resp = await client.get(f"/rest/api/2/issue/{key}", headers=auth_header)
    assert get_resp.status_code == 200
    assert get_resp.json()["fields"]["summary"] == "Issue in imported project"


@pytest.mark.asyncio
async def test_config_import_idempotent(client: httpx.AsyncClient, auth_header: dict):
    """Importing the same config twice succeeds without errors or duplicates."""
    resp1 = await _import_config(client, auth_header)
    assert resp1.status_code == 200
    assert resp1.json()["errors"] == []

    resp2 = await _import_config(client, auth_header)
    assert resp2.status_code == 200
    assert resp2.json()["errors"] == []
    assert resp2.json()["projects"] == 1


@pytest.mark.asyncio
async def test_config_import_rejects_bad_version(client: httpx.AsyncClient, auth_header: dict):
    """Endpoint rejects configs with version != 1.0."""
    bad_config = {**MINIMAL_CONFIG, "version": "99.0"}
    resp = await _import_config(client, auth_header, bad_config)
    assert resp.status_code == 400
