import pytest
import httpx

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}

async def _create_issue(client, project="RHOAIENG", summary="Test", issuetype="Bug"):
    resp = await client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": project}, "summary": summary, "issuetype": {"name": issuetype}}
    }, headers=AUTH)
    return resp.json()

@pytest.mark.asyncio
async def test_get_watchers_empty(client):
    """GET watchers for a new issue returns 0 watchers."""
    issue = await _create_issue(client)
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}/watchers", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["watchCount"] == 0

@pytest.mark.asyncio
async def test_add_watcher(client):
    """POST watchers adds the current user as a watcher."""
    issue = await _create_issue(client)
    resp = await client.post(
        f"/rest/api/2/issue/{issue['key']}/watchers",
        content='"admin"',
        headers={**AUTH, "Content-Type": "application/json"},
    )
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}/watchers", headers=AUTH)
    assert get_resp.json()["watchCount"] == 1

@pytest.mark.asyncio
async def test_remove_watcher(client):
    """DELETE watchers removes the user."""
    issue = await _create_issue(client)
    await client.post(
        f"/rest/api/2/issue/{issue['key']}/watchers",
        content='"admin"',
        headers={**AUTH, "Content-Type": "application/json"},
    )

    resp = await client.delete(
        f"/rest/api/2/issue/{issue['key']}/watchers?username=admin",
        headers=AUTH,
    )
    assert resp.status_code == 204

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}/watchers", headers=AUTH)
    assert get_resp.json()["watchCount"] == 0

@pytest.mark.asyncio
async def test_add_watcher_idempotent(client):
    """Adding the same watcher twice doesn't duplicate."""
    issue = await _create_issue(client)
    for _ in range(2):
        await client.post(
            f"/rest/api/2/issue/{issue['key']}/watchers",
            content='"admin"',
            headers={**AUTH, "Content-Type": "application/json"},
        )

    get_resp = await client.get(f"/rest/api/2/issue/{issue['key']}/watchers", headers=AUTH)
    assert get_resp.json()["watchCount"] == 1
