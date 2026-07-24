"""Tests for Issue Properties CRUD, JQL, and expansion."""

import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


async def _create_issue(client, project="RHOAIENG", summary="Test"):
    resp = await client.post(
        "/rest/api/2/issue",
        json={"fields": {"project": {"key": project}, "summary": summary, "issuetype": {"name": "Bug"}}},
        headers=AUTH,
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# REST API v2 — CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_property_creates_new(client):
    """PUT on a new property key returns 201."""
    issue = await _create_issue(client, summary="prop create")
    resp = await client.put(
        f"/rest/api/2/issue/{issue['key']}/properties/my.prop",
        json={"hello": "world"},
        headers=AUTH,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_set_property_updates_existing(client):
    """PUT on an existing property key returns 200."""
    issue = await _create_issue(client, summary="prop update")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/my.prop", json={"v": 1}, headers=AUTH)

    resp = await client.put(f"/rest/api/2/issue/{key}/properties/my.prop", json={"v": 2}, headers=AUTH)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_property(client):
    """GET returns the key and value."""
    issue = await _create_issue(client, summary="prop get")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/color", json={"r": 255, "g": 0, "b": 0}, headers=AUTH)

    resp = await client.get(f"/rest/api/2/issue/{key}/properties/color", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "color"
    assert data["value"] == {"r": 255, "g": 0, "b": 0}


@pytest.mark.asyncio
async def test_get_property_keys(client):
    """GET on the properties collection returns the keys list."""
    issue = await _create_issue(client, summary="prop keys")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/alpha", json="a", headers=AUTH)
    await client.put(f"/rest/api/2/issue/{key}/properties/beta", json="b", headers=AUTH)

    resp = await client.get(f"/rest/api/2/issue/{key}/properties", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "keys" in data
    prop_keys = sorted([k["key"] for k in data["keys"]])
    assert prop_keys == ["alpha", "beta"]
    for entry in data["keys"]:
        assert "self" in entry


@pytest.mark.asyncio
async def test_delete_property(client):
    """DELETE removes the property and returns 204."""
    issue = await _create_issue(client, summary="prop delete")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/temp", json=42, headers=AUTH)

    resp = await client.delete(f"/rest/api/2/issue/{key}/properties/temp", headers=AUTH)
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{key}/properties/temp", headers=AUTH)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_property_returns_404(client):
    """GET on a missing property key returns 404."""
    issue = await _create_issue(client, summary="prop 404")
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}/properties/nope", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_property_returns_404(client):
    """DELETE on a missing property key returns 404."""
    issue = await _create_issue(client, summary="prop del 404")
    resp = await client.delete(f"/rest/api/2/issue/{issue['key']}/properties/nope", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_property_on_nonexistent_issue_returns_404(client):
    """Operations on a nonexistent issue return 404."""
    resp = await client.put(
        "/rest/api/2/issue/NONEXIST-999/properties/x",
        json={"a": 1},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_property_value_types(client):
    """Properties can store any valid JSON type: object, array, string, number, boolean, null."""
    issue = await _create_issue(client, summary="prop types")
    key = issue["key"]

    test_values = [
        ("obj", {"nested": {"deep": True}}),
        ("arr", [1, "two", None]),
        ("str", "plain string"),
        ("num", 42),
        ("float", 3.14),
        ("bool", True),
    ]

    for prop_key, value in test_values:
        put_resp = await client.put(
            f"/rest/api/2/issue/{key}/properties/{prop_key}",
            json=value,
            headers=AUTH,
        )
        assert put_resp.status_code == 201, f"Failed to set {prop_key}"

        get_resp = await client.get(f"/rest/api/2/issue/{key}/properties/{prop_key}", headers=AUTH)
        assert get_resp.status_code == 200
        assert get_resp.json()["value"] == value, f"Roundtrip failed for {prop_key}"


@pytest.mark.asyncio
async def test_property_null_value(client):
    """Properties can store JSON null (sent as literal 'null' body)."""
    issue = await _create_issue(client, summary="prop null")
    key = issue["key"]

    put_resp = await client.put(
        f"/rest/api/2/issue/{key}/properties/nullable",
        content=b"null",
        headers={**AUTH, "Content-Type": "application/json"},
    )
    assert put_resp.status_code == 201

    get_resp = await client.get(f"/rest/api/2/issue/{key}/properties/nullable", headers=AUTH)
    assert get_resp.status_code == 200
    assert get_resp.json()["value"] is None


@pytest.mark.asyncio
async def test_property_deleted_with_issue(client):
    """Properties are cascade-deleted when the issue is deleted."""
    issue = await _create_issue(client, summary="cascade delete")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/keep", json="yes", headers=AUTH)

    del_resp = await client.delete(f"/rest/api/2/issue/{key}", headers=AUTH)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{key}/properties/keep", headers=AUTH)
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# REST API v3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_properties_via_v3(client):
    """Full CRUD cycle via /rest/api/3/ should work (middleware rewrite)."""
    issue = await _create_issue(client, summary="v3 props")
    key = issue["key"]

    put_resp = await client.put(
        f"/rest/api/3/issue/{key}/properties/v3key",
        json={"version": 3},
        headers=AUTH,
    )
    assert put_resp.status_code == 201

    get_resp = await client.get(f"/rest/api/3/issue/{key}/properties/v3key", headers=AUTH)
    assert get_resp.status_code == 200
    assert get_resp.json()["value"] == {"version": 3}

    keys_resp = await client.get(f"/rest/api/3/issue/{key}/properties", headers=AUTH)
    assert keys_resp.status_code == 200
    assert len(keys_resp.json()["keys"]) == 1

    del_resp = await client.delete(f"/rest/api/3/issue/{key}/properties/v3key", headers=AUTH)
    assert del_resp.status_code == 204


# ---------------------------------------------------------------------------
# Issue GET expansion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expand_properties_on_get_issue(client):
    """GET /issue/{key}?expand=properties includes property keys in response."""
    issue = await _create_issue(client, summary="expand props")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/foo", json="bar", headers=AUTH)

    resp = await client.get(f"/rest/api/2/issue/{key}?expand=properties", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "properties" in data
    assert "keys" in data["properties"]
    prop_keys = [k["key"] for k in data["properties"]["keys"]]
    assert "foo" in prop_keys


@pytest.mark.asyncio
async def test_no_properties_without_expand(client):
    """GET /issue/{key} without expand=properties does NOT include properties."""
    issue = await _create_issue(client, summary="no expand")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/foo", json="bar", headers=AUTH)

    resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "properties" not in data


# ---------------------------------------------------------------------------
# JQL support
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jql_property_top_level_match(client):
    """JQL: issue.property[key] = value matches top-level string property."""
    issue = await _create_issue(client, summary="jql prop top")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/env", json="production", headers=AUTH)

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": 'issue.property[env] = "production"'},
        headers=AUTH,
    )
    assert resp.status_code == 200
    keys = [i["key"] for i in resp.json()["issues"]]
    assert key in keys


@pytest.mark.asyncio
async def test_jql_property_nested_path(client):
    """JQL: issue.property[key].nested.path = value matches nested JSON path."""
    issue = await _create_issue(client, summary="jql prop nested")
    key = issue["key"]
    await client.put(
        f"/rest/api/2/issue/{key}/properties/config",
        json={"deploy": {"region": "us-east-1"}},
        headers=AUTH,
    )

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": 'issue.property[config].deploy.region = "us-east-1"'},
        headers=AUTH,
    )
    assert resp.status_code == 200
    keys = [i["key"] for i in resp.json()["issues"]]
    assert key in keys


@pytest.mark.asyncio
async def test_jql_property_no_match(client):
    """JQL: property query returns no results when value doesn't match."""
    issue = await _create_issue(client, summary="jql prop no match")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/env", json="staging", headers=AUTH)

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": 'issue.property[env] = "production"'},
        headers=AUTH,
    )
    assert resp.status_code == 200
    keys = [i["key"] for i in resp.json()["issues"]]
    assert key not in keys


@pytest.mark.asyncio
async def test_jql_property_is_not_empty(client):
    """JQL: issue.property[key] IS NOT EMPTY matches issues with the property set."""
    issue = await _create_issue(client, summary="jql prop not empty")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/tag", json="x", headers=AUTH)

    other = await _create_issue(client, summary="jql prop empty")

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": "issue.property[tag] IS NOT EMPTY"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    keys = [i["key"] for i in resp.json()["issues"]]
    assert key in keys
    assert other["key"] not in keys


# ---------------------------------------------------------------------------
# Import service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_issue_with_properties(client):
    """Importing an issue with a 'properties' dict creates IssueProperty rows."""
    issues = [
        {
            "key": "RHOAIENG-9000",
            "summary": "Imported with properties",
            "issue_type": "Task",
            "status": "New",
            "properties": {
                "ci.build": {"buildId": 42, "status": "green"},
                "team.meta": "backend",
            },
        }
    ]
    import_resp = await client.post("/api/admin/import", json={"issues": issues}, headers=AUTH)
    assert import_resp.status_code == 200

    keys_resp = await client.get("/rest/api/2/issue/RHOAIENG-9000/properties", headers=AUTH)
    assert keys_resp.status_code == 200
    prop_keys = sorted([k["key"] for k in keys_resp.json()["keys"]])
    assert prop_keys == ["ci.build", "team.meta"]

    get_resp = await client.get("/rest/api/2/issue/RHOAIENG-9000/properties/ci.build", headers=AUTH)
    assert get_resp.status_code == 200
    assert get_resp.json()["value"] == {"buildId": 42, "status": "green"}


@pytest.mark.asyncio
async def test_jql_property_is_empty(client):
    """JQL: issue.property[key] IS EMPTY matches issues without the property."""
    issue = await _create_issue(client, summary="jql prop has it")
    key = issue["key"]
    await client.put(f"/rest/api/2/issue/{key}/properties/tag", json="x", headers=AUTH)

    other = await _create_issue(client, summary="jql prop missing")

    resp = await client.post(
        "/rest/api/2/search",
        json={"jql": "issue.property[tag] IS EMPTY"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    keys = [i["key"] for i in resp.json()["issues"]]
    assert other["key"] in keys
    assert key not in keys
