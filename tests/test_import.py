import json
import os
import pytest
import httpx

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# --- API import tests (via POST /api/admin/import) ---

@pytest.mark.asyncio
async def test_api_import_single_issue(client):
    """POST /api/admin/import with one issue creates it."""
    issue_data = {
        "key": "APITEST-1",
        "summary": "API import test",
        "status": "New",
        "priority": "Major",
        "issue_type": "Bug",
        "reporter": "Test User",
        "project": {"key": "APITEST", "name": "API Test Project"},
        "labels": ["api-test"],
        "components": [],
        "affects_versions": [],
        "fix_versions": [],
    }

    resp = await client.post("/api/admin/import", json={"issues": [issue_data]}, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 1
    assert data["updated"] == 0
    assert "APITEST" in data["projects_created"]

    # Verify the issue exists via REST API
    issue_resp = await client.get("/rest/api/2/issue/APITEST-1", headers=AUTH)
    assert issue_resp.status_code == 200
    assert issue_resp.json()["fields"]["summary"] == "API import test"


@pytest.mark.asyncio
async def test_api_import_bulk_issues(client):
    """POST /api/admin/import with multiple issues."""
    issues = [
        {
            "key": f"BULK-{i}",
            "summary": f"Bulk issue {i}",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Bulk Reporter",
            "project": {"key": "BULK", "name": "Bulk Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        }
        for i in range(1, 6)
    ]

    resp = await client.post("/api/admin/import", json={"issues": issues}, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 5

    # Verify via search
    search_resp = await client.post("/rest/api/2/search", json={
        "jql": "project = BULK",
        "maxResults": 50,
    }, headers=AUTH)
    assert search_resp.json()["total"] == 5


@pytest.mark.asyncio
async def test_api_import_idempotent(client):
    """Importing the same issue twice updates it instead of duplicating."""
    issue = {
        "key": "IDEM-1",
        "summary": "Original summary",
        "status": "New",
        "priority": "Major",
        "issue_type": "Bug",
        "reporter": "Test User",
        "project": {"key": "IDEM", "name": "Idempotent Project"},
        "labels": [],
        "components": [],
        "affects_versions": [],
        "fix_versions": [],
    }

    # First import
    resp1 = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp1.json()["imported"] == 1

    # Second import with updated summary
    issue["summary"] = "Updated summary"
    resp2 = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp2.json()["updated"] == 1
    assert resp2.json()["imported"] == 0

    # Verify only one issue exists
    search_resp = await client.post("/rest/api/2/search", json={
        "jql": "project = IDEM",
        "maxResults": 50,
    }, headers=AUTH)
    assert search_resp.json()["total"] == 1
    assert search_resp.json()["issues"][0]["fields"]["summary"] == "Updated summary"


@pytest.mark.asyncio
async def test_api_import_auto_creates_entities(client):
    """Import auto-creates projects, users, issue types, statuses, priorities."""
    issue = {
        "key": "NEWENT-1",
        "summary": "Auto-create test",
        "status": "Custom Status",
        "priority": "Custom Priority",
        "issue_type": "Custom Type",
        "assignee": "New Assignee User",
        "reporter": "New Reporter User",
        "project": {"key": "NEWENT", "name": "New Entity Project"},
        "labels": [],
        "components": [],
        "affects_versions": [],
        "fix_versions": [],
    }

    resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "NEWENT" in data["projects_created"]
    assert len(data["users_created"]) >= 2  # assignee + reporter

    # Verify the issue has the correct status
    issue_resp = await client.get("/rest/api/2/issue/NEWENT-1", headers=AUTH)
    assert issue_resp.json()["fields"]["status"]["name"] == "Custom Status"
    assert issue_resp.json()["fields"]["priority"]["name"] == "Custom Priority"
    assert issue_resp.json()["fields"]["issuetype"]["name"] == "Custom Type"


@pytest.mark.asyncio
async def test_api_import_with_labels_and_components(client):
    """Import preserves labels and components."""
    issue = {
        "key": "LCOMP-1",
        "summary": "Labels and components test",
        "status": "New",
        "priority": "Major",
        "issue_type": "Bug",
        "reporter": "Test User",
        "project": {"key": "LCOMP", "name": "Label Component Project"},
        "components": [{"name": "Frontend"}, {"name": "Backend"}],
        "labels": ["urgent", "regression"],
        "affects_versions": [],
        "fix_versions": [{"name": "3.0.0"}],
    }

    resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp.status_code == 200

    issue_resp = await client.get("/rest/api/2/issue/LCOMP-1", headers=AUTH)
    data = issue_resp.json()
    assert set(data["fields"]["labels"]) == {"urgent", "regression"}
    comp_names = {c["name"] for c in data["fields"]["components"]}
    assert comp_names == {"Frontend", "Backend"}
    fv_names = {v["name"] for v in data["fields"]["fixVersions"]}
    assert "3.0.0" in fv_names


@pytest.mark.asyncio
async def test_api_import_with_custom_fields(client):
    """Import maps custom fields correctly."""
    issue = {
        "key": "CFTEST-1",
        "summary": "Custom fields test",
        "status": "New",
        "priority": "Major",
        "issue_type": "Bug",
        "reporter": "Test User",
        "project": {"key": "CFTEST", "name": "Custom Field Project"},
        "labels": [],
        "components": [],
        "affects_versions": [],
        "fix_versions": [],
        "team": "Platform Team",
        "story_points": 5.0,
        "severity": "High",
    }

    resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp.status_code == 200

    issue_resp = await client.get("/rest/api/2/issue/CFTEST-1", headers=AUTH)
    fields = issue_resp.json()["fields"]
    assert fields.get("customfield_12313240") == "Platform Team"  # team
    assert fields.get("customfield_12310243") == 5.0  # story_points
    assert fields.get("customfield_12316142") == "High"  # severity


@pytest.mark.asyncio
async def test_api_import_with_epic_link(client):
    """Import resolves epic_link to parent relationship."""
    issues = [
        {
            "key": "EPIC-1",
            "summary": "Parent Epic",
            "status": "New",
            "priority": "Major",
            "issue_type": "Epic",
            "reporter": "Test User",
            "project": {"key": "EPIC", "name": "Epic Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
        {
            "key": "EPIC-2",
            "summary": "Child Story",
            "status": "New",
            "priority": "Major",
            "issue_type": "Story",
            "reporter": "Test User",
            "project": {"key": "EPIC", "name": "Epic Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
            "epic_link": "EPIC-1",
        },
    ]

    resp = await client.post("/api/admin/import", json={"issues": issues}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    # Verify child has parent
    child_resp = await client.get("/rest/api/2/issue/EPIC-2", headers=AUTH)
    parent = child_resp.json()["fields"]["parent"]
    assert parent is not None
    assert parent["key"] == "EPIC-1"


@pytest.mark.asyncio
async def test_api_import_epic_link_reverse_order(client):
    """Epic link works even when child is imported before parent."""
    issues = [
        {
            "key": "REVEPIC-2",
            "summary": "Child Story (imported first)",
            "status": "New",
            "priority": "Major",
            "issue_type": "Story",
            "reporter": "Test User",
            "project": {"key": "REVEPIC", "name": "Reverse Epic Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
            "epic_link": "REVEPIC-1",
        },
        {
            "key": "REVEPIC-1",
            "summary": "Parent Epic (imported second)",
            "status": "New",
            "priority": "Major",
            "issue_type": "Epic",
            "reporter": "Test User",
            "project": {"key": "REVEPIC", "name": "Reverse Epic Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
    ]

    resp = await client.post("/api/admin/import", json={"issues": issues}, headers=AUTH)
    assert resp.status_code == 200

    child_resp = await client.get("/rest/api/2/issue/REVEPIC-2", headers=AUTH)
    parent = child_resp.json()["fields"]["parent"]
    assert parent is not None
    assert parent["key"] == "REVEPIC-1"


@pytest.mark.asyncio
async def test_api_import_sequence_update(client):
    """After import, creating a new issue gets the next key number."""
    issues = [
        {
            "key": "SEQTEST-10",
            "summary": "Issue 10",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "SEQTEST", "name": "Sequence Test"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
        {
            "key": "SEQTEST-20",
            "summary": "Issue 20",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "SEQTEST", "name": "Sequence Test"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
    ]

    await client.post("/api/admin/import", json={"issues": issues}, headers=AUTH)

    # Create a new issue via API - should get key SEQTEST-21
    create_resp = await client.post("/rest/api/2/issue", json={
        "fields": {
            "project": {"key": "SEQTEST"},
            "summary": "New issue after import",
            "issuetype": {"name": "Bug"},
        }
    }, headers=AUTH)
    assert create_resp.status_code == 201
    new_key = create_resp.json()["key"]
    assert new_key == "SEQTEST-21"


@pytest.mark.asyncio
async def test_api_import_with_resolution(client):
    """Import with a resolution value creates the resolution."""
    issue = {
        "key": "RESOLVED-1",
        "summary": "Resolved issue",
        "status": "Closed",
        "priority": "Major",
        "issue_type": "Bug",
        "reporter": "Test User",
        "project": {"key": "RESOLVED", "name": "Resolved Project"},
        "labels": [],
        "components": [],
        "affects_versions": [],
        "fix_versions": [],
        "resolution": "Won't Fix",
    }

    resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp.status_code == 200

    issue_resp = await client.get("/rest/api/2/issue/RESOLVED-1", headers=AUTH)
    assert issue_resp.json()["fields"]["resolution"]["name"] == "Won't Fix"


@pytest.mark.asyncio
async def test_api_import_searchable_via_jql(client):
    """Imported issues are findable via JQL search."""
    issues = [
        {
            "key": f"JQLTEST-{i}",
            "summary": f"JQL searchable issue {i}",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "assignee": "Search User",
            "reporter": "Test User",
            "project": {"key": "JQLTEST", "name": "JQL Test Project"},
            "labels": ["searchable"],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        }
        for i in range(1, 4)
    ]

    await client.post("/api/admin/import", json={"issues": issues}, headers=AUTH)

    # Search by project
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = JQLTEST",
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.json()["total"] == 3

    # Search by label
    resp2 = await client.post("/rest/api/2/search", json={
        "jql": "project = JQLTEST AND labels = searchable",
        "maxResults": 50,
    }, headers=AUTH)
    assert resp2.json()["total"] == 3
