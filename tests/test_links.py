import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


# Helper to create an issue
async def _create_issue(client, project="RHOAIENG", summary="Test", issuetype="Bug"):
    resp = await client.post(
        "/rest/api/2/issue",
        json={"fields": {"project": {"key": project}, "summary": summary, "issuetype": {"name": issuetype}}},
        headers=AUTH,
    )
    return resp.json()


@pytest.mark.asyncio
async def test_create_issue_link(client):
    """POST /rest/api/2/issueLink creates a link between two issues."""
    i1 = await _create_issue(client, summary="Issue A")
    i2 = await _create_issue(client, summary="Issue B")
    resp = await client.post(
        "/rest/api/2/issueLink",
        json={
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": i1["key"]},
            "outwardIssue": {"key": i2["key"]},
        },
        headers=AUTH,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_link_appears_in_issue_response(client):
    """After creating a link, it appears in the issue's issuelinks field."""
    i1 = await _create_issue(client, summary="Issue A")
    i2 = await _create_issue(client, summary="Issue B")
    await client.post(
        "/rest/api/2/issueLink",
        json={
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": i1["key"]},
            "outwardIssue": {"key": i2["key"]},
        },
        headers=AUTH,
    )

    # Check inward issue shows the link
    resp = await client.get(f"/rest/api/2/issue/{i1['key']}", headers=AUTH)
    data = resp.json()
    links = data["fields"]["issuelinks"]
    assert len(links) >= 1


@pytest.mark.asyncio
async def test_create_duplicate_issue_link_is_idempotent(client):
    """Posting the same issue link twice should not create duplicate relationships."""
    i1 = await _create_issue(client, summary="Issue A")
    i2 = await _create_issue(client, summary="Issue B")
    payload = {
        "type": {"name": "Blocks"},
        "inwardIssue": {"key": i1["key"]},
        "outwardIssue": {"key": i2["key"]},
    }

    first_resp = await client.post("/rest/api/2/issueLink", json=payload, headers=AUTH)
    assert first_resp.status_code == 201
    second_resp = await client.post("/rest/api/2/issueLink", json=payload, headers=AUTH)
    assert second_resp.status_code == 201

    inward_resp = await client.get(f"/rest/api/2/issue/{i1['key']}", headers=AUTH)
    inward_links = inward_resp.json()["fields"]["issuelinks"]
    matching_inward_links = [
        link
        for link in inward_links
        if link["type"]["name"] == "Blocks" and link.get("outwardIssue", {}).get("key") == i2["key"]
    ]
    assert len(matching_inward_links) == 1

    outward_resp = await client.get(f"/rest/api/2/issue/{i2['key']}", headers=AUTH)
    outward_links = outward_resp.json()["fields"]["issuelinks"]
    matching_outward_links = [
        link
        for link in outward_links
        if link["type"]["name"] == "Blocks" and link.get("inwardIssue", {}).get("key") == i1["key"]
    ]
    assert len(matching_outward_links) == 1


@pytest.mark.asyncio
async def test_blocks_link_response_matches_real_jira_direction(client):
    """Real Jira: inward endpoint sees other issue as outwardIssue; outward sees inwardIssue."""
    blocker = await _create_issue(client, summary="Issue A blocks B")
    blocked = await _create_issue(client, summary="Issue B is blocked by A")
    payload = {
        "type": {"name": "Blocks"},
        "inwardIssue": {"key": blocker["key"]},
        "outwardIssue": {"key": blocked["key"]},
    }

    resp = await client.post("/rest/api/2/issueLink", json=payload, headers=AUTH)
    assert resp.status_code == 201

    blocker_resp = await client.get(f"/rest/api/2/issue/{blocker['key']}", headers=AUTH)
    blocker_links = blocker_resp.json()["fields"]["issuelinks"]
    assert any(
        link["type"]["name"] == "Blocks"
        and link.get("outwardIssue", {}).get("key") == blocked["key"]
        for link in blocker_links
    )

    blocked_resp = await client.get(f"/rest/api/2/issue/{blocked['key']}", headers=AUTH)
    blocked_links = blocked_resp.json()["fields"]["issuelinks"]
    assert any(
        link["type"]["name"] == "Blocks"
        and link.get("inwardIssue", {}).get("key") == blocker["key"]
        for link in blocked_links
    )


@pytest.mark.asyncio
async def test_cloners_link_response_matches_real_jira_direction(client):
    """Real Jira: generated strategy stored as inwardIssue sees source as outwardIssue."""
    strategy = await _create_issue(client, project="RHAISTRAT", summary="Generated strategy", issuetype="Feature")
    source_rfe = await _create_issue(
        client,
        project="RHAIRFE",
        summary="Source RFE",
        issuetype="Feature Request",
    )
    payload = {
        "type": {"name": "Cloners"},
        "inwardIssue": {"key": strategy["key"]},
        "outwardIssue": {"key": source_rfe["key"]},
    }

    resp = await client.post("/rest/api/2/issueLink", json=payload, headers=AUTH)
    assert resp.status_code == 201

    strategy_resp = await client.get(f"/rest/api/2/issue/{strategy['key']}", headers=AUTH)
    strategy_links = strategy_resp.json()["fields"]["issuelinks"]
    assert any(
        link["type"]["name"] == "Cloners"
        and link.get("outwardIssue", {}).get("key") == source_rfe["key"]
        for link in strategy_links
    )

    rfe_resp = await client.get(f"/rest/api/2/issue/{source_rfe['key']}", headers=AUTH)
    rfe_links = rfe_resp.json()["fields"]["issuelinks"]
    assert any(
        link["type"]["name"] == "Cloners"
        and link.get("inwardIssue", {}).get("key") == strategy["key"]
        for link in rfe_links
    )


@pytest.mark.asyncio
async def test_delete_issue_link(client):
    """DELETE /rest/api/2/issueLink/{id} removes a link."""
    i1 = await _create_issue(client, summary="Issue A")
    i2 = await _create_issue(client, summary="Issue B")
    await client.post(
        "/rest/api/2/issueLink",
        json={
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": i1["key"]},
            "outwardIssue": {"key": i2["key"]},
        },
        headers=AUTH,
    )

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
    resp = await client.post(
        "/rest/api/2/issueLink",
        json={
            "type": {"name": "Issue split"},
            "inwardIssue": {"key": i1["key"]},
            "outwardIssue": {"key": i2["key"]},
        },
        headers=AUTH,
    )
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
    resp = await client.post(
        "/rest/api/2/issueLink",
        json={
            "type": {"name": "NonexistentType"},
            "inwardIssue": {"key": i1["key"]},
            "outwardIssue": {"key": i2["key"]},
        },
        headers=AUTH,
    )
    assert resp.status_code == 404
