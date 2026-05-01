import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


async def _create_issue(client, project="RHOAIENG", summary="Test"):
    resp = await client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": project}, "summary": summary,
                   "issuetype": {"name": "Bug"}}
    }, headers=AUTH)
    return resp.json()


@pytest.mark.asyncio
async def test_create_remote_link(client):
    issue = await _create_issue(client, summary="Remote link target")
    resp = await client.post(
        f"/rest/api/2/issue/{issue['key']}/remotelink",
        json={"object": {
            "url": "https://github.com/org/repo/pull/42",
            "title": "org/repo#42: Fix the thing",
        }},
        headers=AUTH,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data


@pytest.mark.asyncio
async def test_list_remote_links(client):
    issue = await _create_issue(client, summary="Multiple links")
    await client.post(
        f"/rest/api/2/issue/{issue['key']}/remotelink",
        json={"object": {"url": "https://example.com/a", "title": "Link A"}},
        headers=AUTH,
    )
    await client.post(
        f"/rest/api/2/issue/{issue['key']}/remotelink",
        json={"object": {"url": "https://example.com/b", "title": "Link B"}},
        headers=AUTH,
    )

    resp = await client.get(
        f"/rest/api/2/issue/{issue['key']}/remotelink", headers=AUTH)
    assert resp.status_code == 200
    links = resp.json()
    assert len(links) == 2
    urls = [l["object"]["url"] for l in links]
    assert "https://example.com/a" in urls
    assert "https://example.com/b" in urls


@pytest.mark.asyncio
async def test_get_single_remote_link(client):
    issue = await _create_issue(client, summary="Single link")
    create_resp = await client.post(
        f"/rest/api/2/issue/{issue['key']}/remotelink",
        json={"object": {"url": "https://example.com/c", "title": "Link C"}},
        headers=AUTH,
    )
    link_id = create_resp.json()["id"]

    resp = await client.get(
        f"/rest/api/2/issue/{issue['key']}/remotelink/{link_id}",
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["object"]["url"] == "https://example.com/c"
    assert resp.json()["object"]["title"] == "Link C"


@pytest.mark.asyncio
async def test_delete_remote_link(client):
    issue = await _create_issue(client, summary="Delete link test")
    create_resp = await client.post(
        f"/rest/api/2/issue/{issue['key']}/remotelink",
        json={"object": {"url": "https://example.com/d", "title": "Link D"}},
        headers=AUTH,
    )
    link_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/rest/api/2/issue/{issue['key']}/remotelink/{link_id}",
        headers=AUTH,
    )
    assert del_resp.status_code == 204

    list_resp = await client.get(
        f"/rest/api/2/issue/{issue['key']}/remotelink", headers=AUTH)
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_remote_link_on_nonexistent_issue_returns_404(client):
    resp = await client.post(
        "/rest/api/2/issue/NONEXIST-999/remotelink",
        json={"object": {"url": "https://example.com", "title": "Test"}},
        headers=AUTH,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remote_link_via_api_v3(client):
    """Remote links should work via the /rest/api/3/ path too."""
    issue = await _create_issue(client, summary="V3 link test")
    resp = await client.post(
        f"/rest/api/3/issue/{issue['key']}/remotelink",
        json={"object": {"url": "https://example.com/v3", "title": "V3"}},
        headers=AUTH,
    )
    assert resp.status_code == 201

    list_resp = await client.get(
        f"/rest/api/3/issue/{issue['key']}/remotelink", headers=AUTH)
    assert resp.status_code == 201
    links = list_resp.json()
    assert len(links) == 1
    assert links[0]["object"]["url"] == "https://example.com/v3"
