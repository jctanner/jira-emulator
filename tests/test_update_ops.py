import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


async def _create_issue(client, project="RHOAIENG", summary="Test", issuetype="Bug"):
    resp = await client.post(
        "/rest/api/2/issue",
        json={"fields": {"project": {"key": project}, "summary": summary, "issuetype": {"name": issuetype}}},
        headers=AUTH,
    )
    return resp.json()


@pytest.mark.asyncio
async def test_update_add_label(client):
    """PUT with update.labels[{add}] adds a label."""
    issue = await _create_issue(client)
    resp = await client.put(
        f"/rest/api/2/issue/{issue['key']}", json={"update": {"labels": [{"add": "test-label"}]}}, headers=AUTH
    )
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    assert "test-label" in get_resp.json()["fields"]["labels"]


@pytest.mark.asyncio
async def test_update_remove_label(client):
    """PUT with update.labels[{add},{remove}] adds then removes."""
    issue = await _create_issue(client)
    # Add label
    await client.put(
        f"/rest/api/2/issue/{issue['key']}", json={"update": {"labels": [{"add": "label-to-remove"}]}}, headers=AUTH
    )
    # Remove label
    resp = await client.put(
        f"/rest/api/2/issue/{issue['key']}", json={"update": {"labels": [{"remove": "label-to-remove"}]}}, headers=AUTH
    )
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    assert "label-to-remove" not in get_resp.json()["fields"]["labels"]


@pytest.mark.asyncio
async def test_update_add_component(client):
    """PUT with update.components[{add}] adds a component."""
    issue = await _create_issue(client)
    resp = await client.put(
        f"/rest/api/2/issue/{issue['key']}",
        json={"update": {"components": [{"add": {"name": "Backend"}}]}},
        headers=AUTH,
    )
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    comp_names = [c["name"] for c in get_resp.json()["fields"]["components"]]
    assert "Backend" in comp_names


@pytest.mark.asyncio
async def test_update_add_fix_version(client):
    """PUT with update.fixVersions[{add}] adds a fix version."""
    issue = await _create_issue(client)
    resp = await client.put(
        f"/rest/api/2/issue/{issue['key']}",
        json={"update": {"fixVersions": [{"add": {"name": "1.0.0"}}]}},
        headers=AUTH,
    )
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    fv_names = [v["name"] for v in get_resp.json()["fields"]["fixVersions"]]
    assert "1.0.0" in fv_names


@pytest.mark.asyncio
async def test_update_add_comment(client):
    """PUT with update.comment[{add}] adds a comment."""
    issue = await _create_issue(client)
    resp = await client.put(
        f"/rest/api/2/issue/{issue['key']}",
        json={"update": {"comment": [{"add": {"body": "Comment via update"}}]}},
        headers=AUTH,
    )
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    comments = get_resp.json()["fields"]["comment"]["comments"]
    assert any(c["body"] == "Comment via update" for c in comments)


@pytest.mark.asyncio
async def test_fields_and_update_together(client):
    """PUT with both fields and update applies both."""
    issue = await _create_issue(client, summary="Original")
    resp = await client.put(
        f"/rest/api/2/issue/{issue['key']}",
        json={"fields": {"summary": "Updated Summary"}, "update": {"labels": [{"add": "combined-update"}]}},
        headers=AUTH,
    )
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    data = get_resp.json()
    assert data["fields"]["summary"] == "Updated Summary"
    assert "combined-update" in data["fields"]["labels"]


# ---------------------------------------------------------------------------
# GET /issue/{key}/changelog
# ---------------------------------------------------------------------------


async def _spread_history_seconds(issue_key):
    """Give each history row its own second, so each forms its own history.

    The emulator groups rows by (author, second) into one history, so edits
    made quickly in a test would otherwise merge.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from jira_emulator.database import get_session_factory
    from jira_emulator.models.issue import Issue
    from jira_emulator.models.issue_history import IssueHistory

    async with get_session_factory()() as session:
        issue = (await session.execute(select(Issue).where(Issue.key == issue_key))).scalar_one()
        query = select(IssueHistory).where(IssueHistory.issue_id == issue.id).order_by(IssueHistory.id)
        rows = (await session.execute(query)).scalars().all()
        base = datetime(2026, 1, 1)
        for n, row in enumerate(rows):
            row.created_at = base + timedelta(seconds=n)
        await session.commit()
        return len(rows)


@pytest.mark.parametrize("api", ["2", "3"])
async def test_changelog_route_pages_histories(client, api):
    """GET /issue/{key}/changelog pages the same histories expand=changelog embeds."""
    issue = await _create_issue(client)
    key = issue["key"]
    for label in ("one", "two", "three"):
        resp = await client.put(
            f"/rest/api/{api}/issue/{key}", json={"update": {"labels": [{"add": label}]}}, headers=AUTH
        )
        assert resp.status_code == 204
    count = await _spread_history_seconds(key)
    assert count >= 3

    embedded = (await client.get(f"/rest/api/{api}/issue/{key}?expand=changelog", headers=AUTH)).json()["changelog"]

    first = (await client.get(f"/rest/api/{api}/issue/{key}/changelog?startAt=0&maxResults=2", headers=AUTH)).json()
    assert (first["startAt"], first["maxResults"], first["total"], first["isLast"]) == (0, 2, count, count <= 2)
    rest = (await client.get(f"/rest/api/{api}/issue/{key}/changelog?startAt=2", headers=AUTH)).json()
    assert rest["isLast"] is True

    paged = first["values"] + rest["values"]
    assert [h["id"] for h in paged] == [h["id"] for h in embedded["histories"]]
    assert paged[-1]["items"][0]["field"] == "labels"
    assert "three" in paged[-1]["items"][0]["toString"]


async def test_changelog_route_unknown_issue(client):
    resp = await client.get("/rest/api/2/issue/RHOAIENG-99999/changelog", headers=AUTH)
    assert resp.status_code == 404
