"""Tests for parent/child issue hierarchy."""

import httpx

from tests.conftest import AUTH_HEADER


async def _create_issue(
    client: httpx.AsyncClient,
    project_key: str = "RHOAIENG",
    summary: str = "Test issue",
    issue_type: str = "Story",
    parent_key: str | None = None,
) -> dict:
    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}
    resp = await client.post(
        "/rest/api/2/issue",
        json={"fields": fields},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# REST API v2
# ---------------------------------------------------------------------------


async def test_create_child_issue_v2(client: httpx.AsyncClient):
    """Creating an issue with a parent field sets the parent relationship."""
    parent = await _create_issue(client, summary="Parent")
    child = await _create_issue(client, summary="Child", parent_key=parent["key"])

    resp = await client.get(
        f"/rest/api/2/issue/{child['key']}",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["fields"]["parent"] is not None
    assert data["fields"]["parent"]["key"] == parent["key"]


async def test_subtasks_populated_v2(client: httpx.AsyncClient):
    """Parent issue's subtasks field lists its children."""
    parent = await _create_issue(client, summary="Parent with children")
    child1 = await _create_issue(client, summary="Child 1", parent_key=parent["key"])
    child2 = await _create_issue(client, summary="Child 2", parent_key=parent["key"])

    resp = await client.get(
        f"/rest/api/2/issue/{parent['key']}",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    subtasks = data["fields"]["subtasks"]
    assert len(subtasks) == 2
    subtask_keys = {s["key"] for s in subtasks}
    assert subtask_keys == {child1["key"], child2["key"]}


async def test_subtasks_contain_status_and_priority(client: httpx.AsyncClient):
    """Each subtask entry includes status and priority details."""
    parent = await _create_issue(client, summary="Parent")
    await _create_issue(client, summary="Child", parent_key=parent["key"])

    resp = await client.get(
        f"/rest/api/2/issue/{parent['key']}",
        headers=AUTH_HEADER,
    )
    subtask = resp.json()["fields"]["subtasks"][0]
    assert "fields" in subtask
    assert "status" in subtask["fields"]
    assert "issuetype" in subtask["fields"]
    assert subtask["fields"]["status"] is not None
    assert subtask["fields"]["status"]["statusCategory"] is not None


async def test_subtasks_empty_when_no_children(client: httpx.AsyncClient):
    """An issue without children has an empty subtasks list."""
    issue = await _create_issue(client, summary="No children")

    resp = await client.get(
        f"/rest/api/2/issue/{issue['key']}",
        headers=AUTH_HEADER,
    )
    assert resp.json()["fields"]["subtasks"] == []


async def test_parent_includes_issuetype_name(client: httpx.AsyncClient):
    """The parent reference includes the parent's issue type name."""
    parent = await _create_issue(client, summary="Typed parent", issue_type="Epic")
    child = await _create_issue(client, summary="Child", parent_key=parent["key"])

    resp = await client.get(
        f"/rest/api/2/issue/{child['key']}",
        headers=AUTH_HEADER,
    )
    parent_ref = resp.json()["fields"]["parent"]
    assert parent_ref["fields"]["issuetype"]["name"] == "Epic"


async def test_cross_project_parent(client: httpx.AsyncClient):
    """A child in one project can reference a parent in another project."""
    parent = await _create_issue(client, project_key="RHOAIENG", summary="Cross-project parent")
    child = await _create_issue(
        client,
        project_key="RHAIRFE",
        summary="Cross-project child",
        parent_key=parent["key"],
    )

    resp = await client.get(
        f"/rest/api/2/issue/{child['key']}",
        headers=AUTH_HEADER,
    )
    assert resp.json()["fields"]["parent"]["key"] == parent["key"]

    resp = await client.get(
        f"/rest/api/2/issue/{parent['key']}",
        headers=AUTH_HEADER,
    )
    subtask_keys = {s["key"] for s in resp.json()["fields"]["subtasks"]}
    assert child["key"] in subtask_keys


# ---------------------------------------------------------------------------
# REST API v3
# ---------------------------------------------------------------------------


async def test_subtasks_populated_v3(client: httpx.AsyncClient):
    """v3 endpoint also returns populated subtasks."""
    parent = await _create_issue(client, summary="v3 Parent")
    child = await _create_issue(client, summary="v3 Child", parent_key=parent["key"])

    resp = await client.get(
        f"/rest/api/3/issue/{parent['key']}",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    subtasks = data["fields"]["subtasks"]
    assert len(subtasks) == 1
    assert subtasks[0]["key"] == child["key"]


async def test_parent_ref_v3(client: httpx.AsyncClient):
    """v3 endpoint returns parent reference on child issues."""
    parent = await _create_issue(client, summary="v3 Parent")
    child = await _create_issue(client, summary="v3 Child", parent_key=parent["key"])

    resp = await client.get(
        f"/rest/api/3/issue/{child['key']}",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    parent_ref = resp.json()["fields"]["parent"]
    assert parent_ref["key"] == parent["key"]


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------


async def test_web_issue_detail_shows_children(client: httpx.AsyncClient):
    """The web issue detail page renders the child issues section."""
    parent = await _create_issue(client, summary="Web parent")
    child = await _create_issue(client, summary="Web child", parent_key=parent["key"])

    resp = await client.get(f"/issue/{parent['key']}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.text
    assert "Child Issues (1)" in body
    assert child["key"] in body


async def test_web_issue_detail_shows_parent(client: httpx.AsyncClient):
    """The web issue detail page renders the parent in the sidebar."""
    parent = await _create_issue(client, summary="Web sidebar parent")
    child = await _create_issue(client, summary="Web sidebar child", parent_key=parent["key"])

    resp = await client.get(f"/issue/{child['key']}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.text
    assert parent["key"] in body


async def test_web_issue_detail_no_children_section(client: httpx.AsyncClient):
    """The web page omits the child issues card when there are none."""
    issue = await _create_issue(client, summary="Childless")

    resp = await client.get(f"/issue/{issue['key']}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "Child Issues (" not in resp.text
