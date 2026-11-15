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
        link["type"]["name"] == "Blocks" and link.get("outwardIssue", {}).get("key") == blocked["key"]
        for link in blocker_links
    )

    blocked_resp = await client.get(f"/rest/api/2/issue/{blocked['key']}", headers=AUTH)
    blocked_links = blocked_resp.json()["fields"]["issuelinks"]
    assert any(
        link["type"]["name"] == "Blocks" and link.get("inwardIssue", {}).get("key") == blocker["key"]
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
        link["type"]["name"] == "Cloners" and link.get("outwardIssue", {}).get("key") == source_rfe["key"]
        for link in strategy_links
    )

    rfe_resp = await client.get(f"/rest/api/2/issue/{source_rfe['key']}", headers=AUTH)
    rfe_links = rfe_resp.json()["fields"]["issuelinks"]
    assert any(
        link["type"]["name"] == "Cloners" and link.get("inwardIssue", {}).get("key") == strategy["key"]
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


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
async def test_work_item_split_link_type(client, api):
    """The 'Work item split' type rfe-creator uses is seeded and links issues."""
    types = (await client.get(f"/rest/api/{api}/issueLinkType", headers=AUTH)).json()["issueLinkTypes"]
    split = next(t for t in types if t["name"] == "Work item split")
    assert (split["inward"], split["outward"]) == ("is split from", "split to")

    parent = await _create_issue(client, summary="Parent RFE")
    child = await _create_issue(client, summary="Child RFE")
    resp = await client.post(
        f"/rest/api/{api}/issueLink",
        json={
            "type": {"name": "Work item split"},
            "inwardIssue": {"key": child["key"]},
            "outwardIssue": {"key": parent["key"]},
        },
        headers=AUTH,
    )
    assert resp.status_code == 201

    links = (await client.get(f"/rest/api/{api}/issue/{parent['key']}", headers=AUTH)).json()["fields"]["issuelinks"]
    assert [link["type"]["name"] for link in links] == ["Work item split"]


async def _link(client, api, type_name, source_key, destination_key):
    resp = await client.post(
        f"/rest/api/{api}/issueLink",
        json={
            "type": {"name": type_name},
            "inwardIssue": {"key": source_key},
            "outwardIssue": {"key": destination_key},
        },
        headers=AUTH,
    )
    assert resp.status_code == 201


async def _source_links(client, api, key):
    """Return the issue's links where it is the source, as (key, id) pairs."""
    resp = await client.get(f"/rest/api/{api}/issue/{key}", headers=AUTH)
    return [
        (link["outwardIssue"]["key"], link["id"])
        for link in resp.json()["fields"]["issuelinks"]
        if "outwardIssue" in link
    ]


async def _sequences(source_id):
    from sqlalchemy import select

    from jira_emulator.database import get_session_factory
    from jira_emulator.models.link import IssueLink

    async with get_session_factory()() as db:
        rows = await db.execute(
            select(IssueLink.id, IssueLink.sequence)
            .where(IssueLink.inward_issue_id == source_id)
            .order_by(IssueLink.id)
        )
        return [sequence for _, sequence in rows.all()]


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
async def test_links_keep_their_sequence_order(client, api):
    """New links go after the source's existing ones; GET lists them in sequence order."""
    from sqlalchemy import update

    from jira_emulator.database import get_session_factory
    from jira_emulator.models.link import IssueLink

    source = await _create_issue(client, summary="Source")
    b, c, d, e = [await _create_issue(client, summary=name) for name in "BCDE"]
    # Sequences are per source issue, across link types.
    await _link(client, api, "Blocks", source["key"], b["key"])
    await _link(client, api, "Cloners", source["key"], c["key"])
    await _link(client, api, "Blocks", source["key"], d["key"])
    # A link from another source starts its own sequence.
    await _link(client, api, "Blocks", b["key"], c["key"])
    assert await _sequences(int(b["id"])) == [0]

    links = await _source_links(client, api, source["key"])
    assert [key for key, _ in links] == [b["key"], c["key"], d["key"]]
    assert await _sequences(int(source["id"])) == [0, 1, 2]

    # Deleting a link leaves a gap; the next link still goes last.
    assert (await client.delete(f"/rest/api/{api}/issueLink/{links[1][1]}", headers=AUTH)).status_code == 204
    await _link(client, api, "Relates", source["key"], e["key"])
    assert await _sequences(int(source["id"])) == [0, 2, 3]

    # The order follows sequence, not creation order.
    async with get_session_factory()() as db:
        await db.execute(update(IssueLink).where(IssueLink.id == int(links[0][1])).values(sequence=10))
        await db.commit()
    assert [key for key, _ in await _source_links(client, api, source["key"])] == [d["key"], e["key"], b["key"]]


@pytest.mark.asyncio
async def test_init_db_adds_and_backfills_link_sequence(tmp_path):
    """A database from before link ordering gets the column, numbered in id order per source."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from jira_emulator.database import init_db

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE issue_links (id INTEGER PRIMARY KEY, link_type_id INTEGER NOT NULL,"
                    " inward_issue_id INTEGER NOT NULL, outward_issue_id INTEGER NOT NULL)"
                )
            )
            await conn.execute(
                text("INSERT INTO issue_links VALUES (1, 1, 7, 8), (2, 1, 9, 8), (3, 2, 7, 9), (4, 1, 7, 10)")
            )
        await init_db(engine)
        async with engine.connect() as conn:
            rows = (await conn.execute(text("SELECT id, sequence FROM issue_links ORDER BY id"))).all()
        assert [tuple(row) for row in rows] == [(1, 0), (2, 0), (3, 1), (4, 2)]
    finally:
        await engine.dispose()
