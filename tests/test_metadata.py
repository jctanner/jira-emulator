"""Tests for metadata listing endpoints (priorities, statuses, resolutions, issue types, fields)."""

import httpx

from jira_emulator.config import get_settings
from tests.conftest import AUTH_HEADER

EXPECTED_SERVER_INFO_KEYS = {
    "baseUrl",
    "displayUrl",
    "displayUrlServicedeskHelpCenter",
    "displayUrlCSMHelpSeeker",
    "displayUrlConfluence",
    "version",
    "versionNumbers",
    "deploymentType",
    "buildNumber",
    "buildDate",
    "scmInfo",
    "serverTitle",
    "defaultLocale",
    "serverTimeZone",
}


def _assert_server_info_shape(data: dict) -> None:
    assert data.keys() >= EXPECTED_SERVER_INFO_KEYS
    assert data["defaultLocale"] == {"locale": "en_US"}
    assert isinstance(data["versionNumbers"], list)

    # The emulator must never report a real Atlassian/Red Hat domain.
    for url_field in (
        "baseUrl",
        "displayUrl",
        "displayUrlServicedeskHelpCenter",
        "displayUrlCSMHelpSeeker",
        "displayUrlConfluence",
    ):
        assert "redhat" not in data[url_field].lower()
        assert data[url_field] == "https://jira-emulator.atlassian.net"


async def test_server_info_v2_authenticated(client: httpx.AsyncClient):
    """GET /rest/api/2/serverInfo should return a Jira-compatible payload."""
    resp = await client.get("/rest/api/2/serverInfo", headers=AUTH_HEADER)
    assert resp.status_code == 200
    _assert_server_info_shape(resp.json())


async def test_server_info_v3_authenticated(client: httpx.AsyncClient):
    """GET /rest/api/3/serverInfo should follow the v2 -> v3 compatibility rewrite."""
    resp = await client.get("/rest/api/3/serverInfo", headers=AUTH_HEADER)
    assert resp.status_code == 200
    _assert_server_info_shape(resp.json())


async def test_server_info_unauthenticated_permissive_mode(client: httpx.AsyncClient):
    """In permissive auth mode, serverInfo should succeed without credentials."""
    resp = await client.get("/rest/api/2/serverInfo")
    assert resp.status_code == 200
    _assert_server_info_shape(resp.json())

    resp_v3 = await client.get("/rest/api/3/serverInfo")
    assert resp_v3.status_code == 200
    _assert_server_info_shape(resp_v3.json())


async def test_server_info_unauthenticated_strict_mode(client: httpx.AsyncClient):
    """In strict auth mode, serverInfo should require credentials like other endpoints."""
    get_settings().AUTH_MODE = "strict"
    try:
        resp = await client.get("/rest/api/2/serverInfo")
        assert resp.status_code == 401

        resp_v3 = await client.get("/rest/api/3/serverInfo")
        assert resp_v3.status_code == 401

        authed_resp = await client.get("/rest/api/2/serverInfo", headers=AUTH_HEADER)
        assert authed_resp.status_code == 200
        _assert_server_info_shape(authed_resp.json())
    finally:
        get_settings().AUTH_MODE = "permissive"


async def test_list_priorities_returns_six(client: httpx.AsyncClient):
    """GET /rest/api/2/priority should return exactly 6 seeded priorities."""
    resp = await client.get("/rest/api/2/priority", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 6

    names = {p["name"] for p in data}
    assert "Blocker" in names
    assert "Critical" in names
    assert "Major" in names
    assert "Normal" in names
    assert "Minor" in names
    assert "Undefined" in names

    # Each entry should have the expected keys
    for p in data:
        assert "id" in p
        assert "name" in p
        assert "self" in p


async def test_list_statuses_returns_fourteen(client: httpx.AsyncClient):
    """GET /rest/api/2/status should return exactly 14 seeded statuses."""
    resp = await client.get("/rest/api/2/status", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 14

    names = {s["name"] for s in data}
    assert "New" in names
    assert "In Progress" in names
    assert "Done" in names
    assert "Closed" in names

    # Each status should include a statusCategory dict
    for s in data:
        assert "statusCategory" in s
        cat = s["statusCategory"]
        assert "key" in cat
        assert cat["key"] in {"new", "indeterminate", "done"}


async def test_list_resolutions(client: httpx.AsyncClient):
    """GET /rest/api/2/resolution should return all seeded resolutions."""
    resp = await client.get("/rest/api/2/resolution", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 6

    names = {r["name"] for r in data}
    assert names == {"Done", "Won't Do", "Duplicate", "Cannot Reproduce", "Incomplete", "Obsolete"}


async def test_list_issue_types_returns_eight(client: httpx.AsyncClient):
    """GET /rest/api/2/issuetype should return exactly 8 seeded issue types."""
    resp = await client.get("/rest/api/2/issuetype", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 8

    names = {it["name"] for it in data}
    expected = {
        "Feature Request",
        "Feature",
        "Initiative",
        "Bug",
        "Task",
        "Story",
        "Epic",
        "Sub-task",
    }
    assert names == expected

    # Sub-task should be marked as a subtask
    subtasks = [it for it in data if it["name"] == "Sub-task"]
    assert len(subtasks) == 1
    assert subtasks[0]["subtask"] is True


async def test_list_fields_returns_definitions(client: httpx.AsyncClient):
    """GET /rest/api/2/field should return system + custom field definitions."""
    resp = await client.get("/rest/api/2/field", headers=AUTH_HEADER)
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)

    # There should be at least the 19 system fields defined in fields.py
    assert len(data) >= 19

    # Check that well-known system fields are present
    field_ids = {f["id"] for f in data}
    for expected_id in (
        "summary",
        "status",
        "priority",
        "assignee",
        "reporter",
        "issuetype",
        "project",
        "description",
        "labels",
    ):
        assert expected_id in field_ids, f"Missing system field: {expected_id}"

    # Custom fields from seed data should be present
    assert "customfield_12310243" in field_ids  # Story Points

    # Each field should have the expected structure
    for f in data:
        assert "id" in f
        assert "name" in f
        assert "custom" in f
        assert "schema" in f
