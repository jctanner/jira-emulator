from urllib.parse import quote

import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


async def _create_issue(client, project="RHOAIENG", summary="Test"):
    resp = await client.post(
        "/rest/api/2/issue",
        json={"fields": {"project": {"key": project}, "summary": summary, "issuetype": {"name": "Bug"}}},
        headers=AUTH,
    )
    return resp.json()


@pytest.mark.asyncio
async def test_create_remote_link(client):
    issue = await _create_issue(client, summary="Remote link target")
    resp = await client.post(
        f"/rest/api/2/issue/{issue['key']}/remotelink",
        json={
            "object": {
                "url": "https://github.com/org/repo/pull/42",
                "title": "org/repo#42: Fix the thing",
            }
        },
        headers=AUTH,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "self" in data


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

    resp = await client.get(f"/rest/api/2/issue/{issue['key']}/remotelink", headers=AUTH)
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
    data = resp.json()
    assert data["object"]["url"] == "https://example.com/c"
    assert data["object"]["title"] == "Link C"
    assert "self" in data
    assert "status" in data["object"]


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

    list_resp = await client.get(f"/rest/api/2/issue/{issue['key']}/remotelink", headers=AUTH)
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

    list_resp = await client.get(f"/rest/api/3/issue/{issue['key']}/remotelink", headers=AUTH)
    assert list_resp.status_code == 200
    links = list_resp.json()
    assert len(links) == 1
    assert links[0]["object"]["url"] == "https://example.com/v3"


# --- New tests for spec compliance ---


@pytest.mark.asyncio
async def test_create_without_title_returns_400(client):
    """object.title is required by the spec."""
    issue = await _create_issue(client, summary="Title validation")
    resp = await client.post(
        f"/rest/api/2/issue/{issue['key']}/remotelink",
        json={"object": {"url": "https://example.com/no-title"}},
        headers=AUTH,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_global_id_upsert(client):
    """POST with the same globalId should update, not create a duplicate."""
    issue = await _create_issue(client, summary="Upsert test")
    base = f"/rest/api/2/issue/{issue['key']}/remotelink"
    gid = "system=test&id=1"

    resp1 = await client.post(
        base,
        json={
            "globalId": gid,
            "object": {"url": "https://example.com/v1", "title": "Version 1"},
        },
        headers=AUTH,
    )
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    resp2 = await client.post(
        base,
        json={
            "globalId": gid,
            "object": {"url": "https://example.com/v2", "title": "Version 2"},
        },
        headers=AUTH,
    )
    assert resp2.status_code == 201
    id2 = resp2.json()["id"]
    assert id1 == id2

    links = (await client.get(base, headers=AUTH)).json()
    assert len(links) == 1
    assert links[0]["object"]["url"] == "https://example.com/v2"
    assert links[0]["globalId"] == gid


@pytest.mark.asyncio
async def test_relationship_and_summary_roundtrip(client):
    """globalId, relationship, and object.summary should be stored and returned."""
    issue = await _create_issue(client, summary="Fields roundtrip")
    base = f"/rest/api/2/issue/{issue['key']}/remotelink"

    resp = await client.post(
        base,
        json={
            "globalId": "system=roundtrip&id=1",
            "relationship": "causes",
            "object": {
                "url": "https://example.com/rt",
                "title": "RT Link",
                "summary": "A summary",
            },
        },
        headers=AUTH,
    )
    assert resp.status_code == 201
    link_id = resp.json()["id"]

    data = (await client.get(f"{base}/{link_id}", headers=AUTH)).json()
    assert data["globalId"] == "system=roundtrip&id=1"
    assert data["relationship"] == "causes"
    assert data["object"]["summary"] == "A summary"


@pytest.mark.asyncio
async def test_put_update_by_id(client):
    """PUT replaces a remote link by internal ID."""
    issue = await _create_issue(client, summary="PUT test")
    base = f"/rest/api/2/issue/{issue['key']}/remotelink"

    create_resp = await client.post(
        base,
        json={
            "object": {"url": "https://example.com/old", "title": "Old"},
        },
        headers=AUTH,
    )
    link_id = create_resp.json()["id"]

    put_resp = await client.put(
        f"{base}/{link_id}",
        json={
            "object": {"url": "https://example.com/new", "title": "New"},
        },
        headers=AUTH,
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["id"] == link_id
    assert "self" in put_resp.json()

    data = (await client.get(f"{base}/{link_id}", headers=AUTH)).json()
    assert data["object"]["url"] == "https://example.com/new"
    assert data["object"]["title"] == "New"


@pytest.mark.asyncio
async def test_get_by_global_id(client):
    """GET with globalId query parameter filters to matching link."""
    issue = await _create_issue(client, summary="GET by globalId")
    base = f"/rest/api/2/issue/{issue['key']}/remotelink"
    gid = "system=filter&id=42"

    await client.post(
        base,
        json={
            "object": {"url": "https://example.com/no-gid", "title": "No GID"},
        },
        headers=AUTH,
    )
    await client.post(
        base,
        json={
            "globalId": gid,
            "object": {"url": "https://example.com/with-gid", "title": "With GID"},
        },
        headers=AUTH,
    )

    resp = await client.get(f"{base}?globalId={quote(gid, safe='')}", headers=AUTH)
    assert resp.status_code == 200
    links = resp.json()
    assert len(links) == 1
    assert links[0]["object"]["url"] == "https://example.com/with-gid"


@pytest.mark.asyncio
async def test_delete_by_global_id(client):
    """DELETE with globalId query parameter removes the matching link."""
    issue = await _create_issue(client, summary="DELETE by globalId")
    base = f"/rest/api/2/issue/{issue['key']}/remotelink"
    gid = "system=del&id=99"

    await client.post(
        base,
        json={
            "globalId": gid,
            "object": {"url": "https://example.com/del-gid", "title": "Del GID"},
        },
        headers=AUTH,
    )
    await client.post(
        base,
        json={
            "object": {"url": "https://example.com/keep", "title": "Keep"},
        },
        headers=AUTH,
    )

    del_resp = await client.delete(f"{base}?globalId={quote(gid, safe='')}", headers=AUTH)
    assert del_resp.status_code == 204

    links = (await client.get(base, headers=AUTH)).json()
    assert len(links) == 1
    assert links[0]["object"]["url"] == "https://example.com/keep"


@pytest.mark.asyncio
async def test_get_by_id_response_format(client):
    """GET by ID must include self, status, and relationship."""
    issue = await _create_issue(client, summary="Response format")
    base = f"/rest/api/2/issue/{issue['key']}/remotelink"

    create_resp = await client.post(
        base,
        json={
            "object": {"url": "https://example.com/fmt", "title": "Format"},
        },
        headers=AUTH,
    )
    link_id = create_resp.json()["id"]

    data = (await client.get(f"{base}/{link_id}", headers=AUTH)).json()
    assert "self" in data
    assert data["self"].endswith(f"/remotelink/{link_id}")
    assert data["object"]["status"] == {"icon": {}}
    assert data["relationship"] == "links to"
