import pytest
import httpx

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}

# Helper to create an issue
async def _create_issue(client, project="RHOAIENG", summary="Test", issuetype="Bug"):
    resp = await client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": project}, "summary": summary, "issuetype": {"name": issuetype}}
    }, headers=AUTH)
    return resp.json()

@pytest.mark.asyncio
async def test_create_issue_link(client):
    """POST /rest/api/2/issueLink creates a link between two issues."""
    i1 = await _create_issue(client, summary="Issue A")
    i2 = await _create_issue(client, summary="Issue B")
    resp = await client.post("/rest/api/2/issueLink", json={
        "type": {"name": "Blocks"},
        "inwardIssue": {"key": i1["key"]},
        "outwardIssue": {"key": i2["key"]},
    }, headers=AUTH)
    assert resp.status_code == 201

@pytest.mark.asyncio
async def test_link_appears_in_issue_response(client):
    """After creating a link, it appears in the issue's issuelinks field."""
    i1 = await _create_issue(client, summary="Issue A")
    i2 = await _create_issue(client, summary="Issue B")
    await client.post("/rest/api/2/issueLink", json={
        "type": {"name": "Blocks"},
        "inwardIssue": {"key": i1["key"]},
        "outwardIssue": {"key": i2["key"]},
    }, headers=AUTH)

    # Check inward issue shows the link
    resp = await client.get(f"/rest/api/2/issue/{i1['key']}", headers=AUTH)
    data = resp.json()
    links = data["fields"]["issuelinks"]
    assert len(links) >= 1

@pytest.mark.asyncio
async def test_delete_issue_link(client):
    """DELETE /rest/api/2/issueLink/{id} removes a link."""
    i1 = await _create_issue(client, summary="Issue A")
    i2 = await _create_issue(client, summary="Issue B")
    await client.post("/rest/api/2/issueLink", json={
        "type": {"name": "Blocks"},
        "inwardIssue": {"key": i1["key"]},
        "outwardIssue": {"key": i2["key"]},
    }, headers=AUTH)

    # Get the link ID from the issue
    resp = await client.get(f"/rest/api/2/issue/{i1['key']}", headers=AUTH)
    link_id = resp.json()["fields"]["issuelinks"][0]["id"]

    # Delete it
    del_resp = await client.delete(f"/rest/api/2/issueLink/{link_id}", headers=AUTH)
    assert del_resp.status_code == 204

    # Verify it's gone
    resp2 = await client.get(f"/rest/api/2/issue/{i1['key']}", headers=AUTH)
    assert len(resp2.json()["fields"]["issuelinks"]) == 0

@pytest.mark.asyncio
async def test_list_link_types(client):
    """GET /rest/api/2/issueLinkType returns link types."""
    resp = await client.get("/rest/api/2/issueLinkType", headers=AUTH)
    assert resp.status_code == 200
    link_types = resp.json()["issueLinkTypes"]
    assert len(link_types) >= 3  # Blocks, Clones, Relates
    names = [lt["name"] for lt in link_types]
    assert "Blocks" in names

@pytest.mark.asyncio
async def test_issue_split_link_type(client):
    """POST /rest/api/2/issueLink with 'Issue split' type works."""
    i1 = await _create_issue(client, summary="Parent RFE")
    i2 = await _create_issue(client, summary="Child RFE")
    resp = await client.post("/rest/api/2/issueLink", json={
        "type": {"name": "Issue split"},
        "inwardIssue": {"key": i1["key"]},
        "outwardIssue": {"key": i2["key"]},
    }, headers=AUTH)
    assert resp.status_code == 201

    # Verify link appears on the parent issue
    resp = await client.get(f"/rest/api/2/issue/{i1['key']}", headers=AUTH)
    links = resp.json()["fields"]["issuelinks"]
    assert len(links) == 1
    assert links[0]["type"]["name"] == "Issue split"


@pytest.mark.asyncio
async def test_create_link_invalid_type_returns_404(client):
    """POST /rest/api/2/issueLink with invalid link type returns 404."""
    i1 = await _create_issue(client, summary="Issue A")
    i2 = await _create_issue(client, summary="Issue B")
    resp = await client.post("/rest/api/2/issueLink", json={
        "type": {"name": "NonexistentType"},
        "inwardIssue": {"key": i1["key"]},
        "outwardIssue": {"key": i2["key"]},
    }, headers=AUTH)
    assert resp.status_code == 404
