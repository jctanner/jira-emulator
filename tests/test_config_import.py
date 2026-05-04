"""Tests for v1.0 project configuration import."""

import json

import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


def _minimal_config(**overrides):
    """Build a minimal v1.0 project config for testing."""
    config = {
        "version": "1.0",
        "metadata": {
            "exported_at": "2026-05-01T00:00:00+00:00",
            "source": "https://example.atlassian.net",
            "project": "CFGTEST",
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
                "name": "CFGTEST Workflow",
                "statuses": [
                    {"status_id": "1", "sequence": 1},
                    {"status_id": "2", "sequence": 2},
                    {"status_id": "3", "sequence": 3},
                ],
            },
        ],
        "project": {
            "key": "CFGTEST",
            "name": "Config Test Project",
            "description": "A project for config import tests",
            "issue_types": ["Bug", "Task"],
            "workflows": [
                {"issue_type": "Bug", "workflow_id": "wf1"},
                {"issue_type": "Task", "workflow_id": "wf1"},
            ],
        },
    }
    config.update(overrides)
    return config


@pytest.mark.asyncio
async def test_import_project_config_via_api(client):
    """POST /api/admin/import/project-config imports all entity types."""
    config = _minimal_config()
    content = json.dumps(config).encode()

    resp = await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["statuses"] == 3
    assert data["issue_types"] == 2
    assert data["priorities"] == 2
    assert data["resolutions"] == 2
    assert data["link_types"] == 1
    assert data["custom_fields"] == 1
    assert data["workflows"] == 1
    assert data["projects"] == 1
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_import_rejects_bad_version(client):
    """POST /api/admin/import/project-config rejects non-1.0 version."""
    config = _minimal_config(version="2.0")
    content = json.dumps(config).encode()

    resp = await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )
    assert resp.status_code == 400
    assert "version" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_rejects_invalid_json(client):
    """POST /api/admin/import/project-config rejects invalid JSON."""
    resp = await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", b"not json", "application/json")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_imported_project_visible_via_api(client):
    """Imported project shows up in GET /rest/api/2/project."""
    config = _minimal_config()
    config["project"]["key"] = "CFGVIS"
    config["project"]["name"] = "Visible Project"
    content = json.dumps(config).encode()

    await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )

    resp = await client.get("/rest/api/2/project/CFGVIS", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Visible Project"


@pytest.mark.asyncio
async def test_imported_statuses_visible(client):
    """Imported statuses show up in GET /rest/api/2/status."""
    config = _minimal_config()
    config["statuses"] = [
        {"status_id": "unique1", "name": "UniqueStatusXYZ", "status_category": "new"},
    ]
    config["workflows"] = []
    config["project"] = {}
    content = json.dumps(config).encode()

    await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )

    resp = await client.get("/rest/api/2/status", headers=AUTH)
    names = [s["name"] for s in resp.json()]
    assert "UniqueStatusXYZ" in names


@pytest.mark.asyncio
async def test_imported_priorities_visible(client):
    """Imported priorities show up in GET /rest/api/2/priority."""
    config = _minimal_config()
    config["priorities"] = [{"name": "UniquePriorityABC", "sort_order": 99}]
    config["workflows"] = []
    config["project"] = {}
    content = json.dumps(config).encode()

    await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )

    resp = await client.get("/rest/api/2/priority", headers=AUTH)
    names = [p["name"] for p in resp.json()]
    assert "UniquePriorityABC" in names


@pytest.mark.asyncio
async def test_import_idempotent(client):
    """Importing the same config twice does not duplicate entities."""
    config = _minimal_config()
    config["project"]["key"] = "CFGIDEM"
    config["project"]["name"] = "Idempotent Project"
    content = json.dumps(config).encode()

    resp1 = await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["projects"] == 1
    assert data2["errors"] == []

    # Only one project with this key exists
    resp = await client.get("/rest/api/2/project/CFGIDEM", headers=AUTH)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_import_creates_issue_sequence(client):
    """After config import, creating an issue gets key PROJ-1."""
    config = _minimal_config()
    config["project"]["key"] = "CFGSEQ"
    config["project"]["name"] = "Sequence Test"
    content = json.dumps(config).encode()

    await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )

    create_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "CFGSEQ"},
                "summary": "First issue after config import",
                "issuetype": {"name": "Bug"},
            },
        },
        headers=AUTH,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["key"] == "CFGSEQ-1"


@pytest.mark.asyncio
async def test_import_workflow_transitions(client):
    """Workflow transitions are generated from the ordered status list."""
    config = _minimal_config()
    config["project"]["key"] = "CFGWF"
    config["project"]["name"] = "Workflow Test"
    content = json.dumps(config).encode()

    await client.post(
        "/api/admin/import/project-config",
        headers=AUTH,
        files={"file": ("config.json", content, "application/json")},
    )

    # Create an issue in this project
    create_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "CFGWF"},
                "summary": "Workflow test issue",
                "issuetype": {"name": "Bug"},
            },
        },
        headers=AUTH,
    )
    assert create_resp.status_code == 201
    key = create_resp.json()["key"]

    # Check available transitions
    trans_resp = await client.get(f"/rest/api/2/issue/{key}/transitions", headers=AUTH)
    assert trans_resp.status_code == 200
    transition_names = [t["name"] for t in trans_resp.json()["transitions"]]
    assert len(transition_names) > 0
