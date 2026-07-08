import json
import os
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest

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
    search_resp = await client.post(
        "/rest/api/2/search",
        json={
            "jql": "project = BULK",
            "maxResults": 50,
        },
        headers=AUTH,
    )
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
    search_resp = await client.post(
        "/rest/api/2/search",
        json={
            "jql": "project = IDEM",
            "maxResults": 50,
        },
        headers=AUTH,
    )
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
    create_resp = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "SEQTEST"},
                "summary": "New issue after import",
                "issuetype": {"name": "Bug"},
            }
        },
        headers=AUTH,
    )
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
    resp = await client.post(
        "/rest/api/2/search",
        json={
            "jql": "project = JQLTEST",
            "maxResults": 50,
        },
        headers=AUTH,
    )
    assert resp.json()["total"] == 3

    # Search by label
    resp2 = await client.post(
        "/rest/api/2/search",
        json={
            "jql": "project = JQLTEST AND labels = searchable",
            "maxResults": 50,
        },
        headers=AUTH,
    )
    assert resp2.json()["total"] == 3


# --- Archive import tests ---


def _create_test_archive(archive_type: str, issues: list[dict]) -> str:
    """Create a temporary archive (.zip or .tar.gz) with JSON files.

    Returns the path to the temporary archive file.
    """
    temp_dir = tempfile.mkdtemp()

    # Create nested directory structure with JSON files
    data_dir = Path(temp_dir) / "data"
    data_dir.mkdir()

    subdir = data_dir / "nested"
    subdir.mkdir()

    # Write some issues to root level
    if len(issues) > 0:
        with open(data_dir / "issues1.json", "w") as f:
            json.dump(issues[: len(issues) // 2] if len(issues) > 1 else issues, f)

    # Write some issues to nested directory
    if len(issues) > 1:
        with open(subdir / "issues2.json", "w") as f:
            json.dump(issues[len(issues) // 2 :], f)

    # Create the archive
    if archive_type == "zip":
        archive_path = os.path.join(temp_dir, "test.zip")
        with zipfile.ZipFile(archive_path, "w") as zf:
            for json_file in data_dir.rglob("*.json"):
                arcname = json_file.relative_to(temp_dir)
                zf.write(json_file, arcname=arcname)
    elif archive_type == "tar.gz":
        archive_path = os.path.join(temp_dir, "test.tar.gz")
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(data_dir, arcname="data")
    else:
        raise ValueError(f"Unsupported archive type: {archive_type}")

    return archive_path


@pytest.mark.asyncio
async def test_api_import_zip_archive(client):
    """POST /api/admin/import/file with a .zip archive imports all JSON files."""
    issues = [
        {
            "key": "ZIPTEST-1",
            "summary": "Issue from zip 1",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "ZIPTEST", "name": "Zip Test Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
        {
            "key": "ZIPTEST-2",
            "summary": "Issue from zip 2",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "ZIPTEST", "name": "Zip Test Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
    ]

    archive_path = _create_test_archive("zip", issues)

    try:
        with open(archive_path, "rb") as f:
            resp = await client.post(
                "/api/admin/import/file",
                headers=AUTH,
                files={"file": ("test.zip", f, "application/zip")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2
        assert "ZIPTEST" in data["projects_created"]

        # Verify issues exist
        issue_resp = await client.get("/rest/api/2/issue/ZIPTEST-1", headers=AUTH)
        assert issue_resp.status_code == 200
        assert issue_resp.json()["fields"]["summary"] == "Issue from zip 1"
    finally:
        # Clean up
        if os.path.exists(archive_path):
            os.remove(archive_path)


@pytest.mark.asyncio
async def test_api_import_targz_archive(client):
    """POST /api/admin/import/file with a .tar.gz archive imports all JSON files."""
    issues = [
        {
            "key": "TARTEST-1",
            "summary": "Issue from tar.gz 1",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "TARTEST", "name": "Tar Test Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
        {
            "key": "TARTEST-2",
            "summary": "Issue from tar.gz 2",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "TARTEST", "name": "Tar Test Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
    ]

    archive_path = _create_test_archive("tar.gz", issues)

    try:
        with open(archive_path, "rb") as f:
            resp = await client.post(
                "/api/admin/import/file",
                headers=AUTH,
                files={"file": ("test.tar.gz", f, "application/gzip")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2
        assert "TARTEST" in data["projects_created"]

        # Verify issues exist
        issue_resp = await client.get("/rest/api/2/issue/TARTEST-1", headers=AUTH)
        assert issue_resp.status_code == 200
        assert issue_resp.json()["fields"]["summary"] == "Issue from tar.gz 1"
    finally:
        # Clean up
        if os.path.exists(archive_path):
            os.remove(archive_path)


@pytest.mark.asyncio
async def test_api_import_archive_recursive_search(client):
    """Archive import recursively finds JSON files in subdirectories."""
    issues = [
        {
            "key": "RECTEST-1",
            "summary": "Root level issue",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "RECTEST", "name": "Recursive Test Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
        {
            "key": "RECTEST-2",
            "summary": "Nested directory issue",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "RECTEST", "name": "Recursive Test Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
    ]

    archive_path = _create_test_archive("zip", issues)

    try:
        with open(archive_path, "rb") as f:
            resp = await client.post(
                "/api/admin/import/file",
                headers=AUTH,
                files={"file": ("recursive.zip", f, "application/zip")},
            )

        assert resp.status_code == 200
        data = resp.json()
        # Both issues should be found despite being in different directories
        assert data["imported"] == 2
    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)


@pytest.mark.asyncio
async def test_api_import_json_file(client):
    """POST /api/admin/import/file with a plain JSON file works."""
    issues = [
        {
            "key": "JSONFILE-1",
            "summary": "Issue from JSON file",
            "status": "New",
            "priority": "Major",
            "issue_type": "Bug",
            "reporter": "Test User",
            "project": {"key": "JSONFILE", "name": "JSON File Project"},
            "labels": [],
            "components": [],
            "affects_versions": [],
            "fix_versions": [],
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(issues, f)
        json_path = f.name

    try:
        with open(json_path, "rb") as f:
            resp = await client.post(
                "/api/admin/import/file",
                headers=AUTH,
                files={"file": ("test.json", f, "application/json")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1
        assert "JSONFILE" in data["projects_created"]
    finally:
        if os.path.exists(json_path):
            os.remove(json_path)


# --- Jira REST API format import tests ---


def _jira_api_issue(key, summary, **overrides):
    """Build a minimal issue in Jira REST API v2 format (nested fields)."""
    project_key = key.rsplit("-", 1)[0]
    reporter_name = overrides.pop("reporter", "Test Reporter")
    assignee_name = overrides.pop("assignee", None)

    fields = {
        "summary": summary,
        "issuetype": {"id": "1", "name": overrides.pop("issuetype", "Bug")},
        "status": {"id": "1", "name": overrides.pop("status", "New")},
        "priority": {"id": "1", "name": overrides.pop("priority", "Major")},
        "project": {"key": project_key, "name": overrides.pop("project_name", project_key)},
        "reporter": {"accountId": "abc123", "displayName": reporter_name} if reporter_name else None,
        "assignee": {"accountId": "def456", "displayName": assignee_name} if assignee_name else None,
        "labels": overrides.pop("labels", []),
        "components": overrides.pop("components", []),
        "fixVersions": overrides.pop("fixVersions", []),
        "versions": overrides.pop("versions", []),
        "resolution": None,
        "created": overrides.pop("created", "2026-01-15T10:00:00.000+0000"),
        "updated": overrides.pop("updated", "2026-01-15T12:00:00.000+0000"),
        "duedate": overrides.pop("duedate", None),
        "comment": overrides.pop("comment", {"comments": [], "total": 0}),
        "issuelinks": overrides.pop("issuelinks", []),
    }
    parent = overrides.pop("parent", None)
    if parent:
        fields["parent"] = parent
    resolution_name = overrides.pop("resolution_name", None)
    if resolution_name:
        fields["resolution"] = {"name": resolution_name}
    fields.update(overrides)
    return {"key": key, "id": "99999", "fields": fields}


@pytest.mark.asyncio
async def test_api_import_jira_api_format(client):
    """Import a single issue in Jira REST API format (nested fields)."""
    issue = _jira_api_issue(
        "JAPI-1", "Jira API format issue",
        issuetype="Story",
        status="In Progress",
        priority="Critical",
        reporter="Jane Doe",
        assignee="John Smith",
        labels=["imported", "test"],
        components=[{"id": "1", "name": "Backend"}],
        fixVersions=[{"id": "1", "name": "2.0.0"}],
    )

    resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 1
    assert "JAPI" in data["projects_created"]

    issue_resp = await client.get("/rest/api/2/issue/JAPI-1", headers=AUTH)
    assert issue_resp.status_code == 200
    fields = issue_resp.json()["fields"]
    assert fields["summary"] == "Jira API format issue"
    assert fields["issuetype"]["name"] == "Story"
    assert fields["status"]["name"] == "In Progress"
    assert fields["priority"]["name"] == "Critical"
    assert fields["assignee"]["displayName"] == "John Smith"
    assert fields["reporter"]["displayName"] == "Jane Doe"
    assert set(fields["labels"]) == {"imported", "test"}
    assert any(c["name"] == "Backend" for c in fields["components"])
    assert any(v["name"] == "2.0.0" for v in fields["fixVersions"])


@pytest.mark.asyncio
async def test_api_import_jira_export_wrapper(client):
    """Import issues wrapped in the export envelope format."""
    issues = [
        _jira_api_issue("WRAP-1", "Wrapped issue 1"),
        _jira_api_issue("WRAP-2", "Wrapped issue 2"),
    ]
    payload = {
        "metadata": {
            "exported_at": "2026-06-10T00:00:00+00:00",
            "source": "https://example.atlassian.net",
            "project": "WRAP",
            "jql": "project = WRAP",
            "total": 2,
        },
        "issues": issues,
    }

    resp = await client.post("/api/admin/import", json=payload, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2

    for key in ["WRAP-1", "WRAP-2"]:
        issue_resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH)
        assert issue_resp.status_code == 200


@pytest.mark.asyncio
async def test_api_import_file_jira_export_wrapper(client):
    """File upload with Jira export envelope format."""
    issues = [
        _jira_api_issue("FWRAP-1", "File wrapped issue"),
    ]
    payload = {
        "metadata": {
            "exported_at": "2026-06-10T00:00:00+00:00",
            "source": "https://example.atlassian.net",
            "project": "FWRAP",
            "total": 1,
        },
        "issues": issues,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        json_path = f.name

    try:
        with open(json_path, "rb") as f:
            resp = await client.post(
                "/api/admin/import/file",
                headers=AUTH,
                files={"file": ("export.json", f, "application/json")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1

        issue_resp = await client.get("/rest/api/2/issue/FWRAP-1", headers=AUTH)
        assert issue_resp.status_code == 200
        assert issue_resp.json()["fields"]["summary"] == "File wrapped issue"
    finally:
        if os.path.exists(json_path):
            os.remove(json_path)


@pytest.mark.asyncio
async def test_api_import_jira_api_with_comments(client):
    """Comments from Jira REST API format are imported."""
    issue = _jira_api_issue(
        "CTEST-1", "Issue with comments",
        comment={
            "comments": [
                {
                    "id": "100",
                    "author": {"accountId": "abc", "displayName": "Alice"},
                    "body": "First comment",
                    "created": "2026-01-15T10:30:00.000+0000",
                    "updated": "2026-01-15T10:30:00.000+0000",
                },
                {
                    "id": "101",
                    "author": {"accountId": "def", "displayName": "Bob"},
                    "body": "Second comment",
                    "created": "2026-01-15T11:00:00.000+0000",
                    "updated": "2026-01-15T11:00:00.000+0000",
                },
            ],
            "total": 2,
        },
    )

    resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1

    issue_resp = await client.get("/rest/api/2/issue/CTEST-1", headers=AUTH)
    assert issue_resp.status_code == 200
    comments = issue_resp.json()["fields"]["comment"]["comments"]
    assert len(comments) == 2
    assert comments[0]["body"] == "First comment"
    assert comments[1]["body"] == "Second comment"


@pytest.mark.asyncio
async def test_api_import_jira_api_with_links(client):
    """Issue links from Jira REST API format are imported."""
    issue_a = _jira_api_issue("LNKTEST-1", "Link source")
    issue_b = _jira_api_issue(
        "LNKTEST-2", "Link target",
        issuelinks=[
            {
                "id": "500",
                "type": {
                    "id": "10001",
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                "outwardIssue": {
                    "id": "1",
                    "key": "LNKTEST-1",
                    "fields": {"summary": "Link source"},
                },
            }
        ],
    )

    resp = await client.post(
        "/api/admin/import", json={"issues": [issue_a, issue_b]}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    issue_resp = await client.get("/rest/api/2/issue/LNKTEST-2", headers=AUTH)
    assert issue_resp.status_code == 200
    links = issue_resp.json()["fields"]["issuelinks"]
    assert len(links) >= 1
    assert any(link.get("outwardIssue", {}).get("key") == "LNKTEST-1" for link in links)

    source_resp = await client.get("/rest/api/2/issue/LNKTEST-1", headers=AUTH)
    assert source_resp.status_code == 200
    source_links = source_resp.json()["fields"]["issuelinks"]
    assert any(link.get("inwardIssue", {}).get("key") == "LNKTEST-2" for link in source_links)


@pytest.mark.asyncio
async def test_api_import_jira_api_with_inward_link_preserves_direction(client):
    """Imported inwardIssue links keep the source issue on the inward side."""
    issue_a = _jira_api_issue(
        "INLINK-1",
        "Blocked issue",
        issuelinks=[
            {
                "type": {
                    "id": "10001",
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                "inwardIssue": {
                    "id": "2",
                    "key": "INLINK-2",
                    "fields": {"summary": "Blocker issue"},
                },
            }
        ],
    )
    issue_b = _jira_api_issue("INLINK-2", "Blocker issue")

    resp = await client.post(
        "/api/admin/import", json={"issues": [issue_a, issue_b]}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    blocked_resp = await client.get("/rest/api/2/issue/INLINK-1", headers=AUTH)
    assert blocked_resp.status_code == 200
    blocked_links = blocked_resp.json()["fields"]["issuelinks"]
    assert any(link.get("inwardIssue", {}).get("key") == "INLINK-2" for link in blocked_links)

    blocker_resp = await client.get("/rest/api/2/issue/INLINK-2", headers=AUTH)
    assert blocker_resp.status_code == 200
    blocker_links = blocker_resp.json()["fields"]["issuelinks"]
    assert any(link.get("outwardIssue", {}).get("key") == "INLINK-1" for link in blocker_links)


@pytest.mark.asyncio
async def test_api_import_jira_api_with_cloners_link_preserves_direction(client):
    """Imported Cloners links keep the generated issue as cloning the source."""
    source = _jira_api_issue("CLONEIMP-1", "Source RFE")
    derived = _jira_api_issue(
        "CLONEIMP-2",
        "Generated strategy",
        issuelinks=[
            {
                "type": {
                    "id": "10002",
                    "name": "Cloners",
                    "inward": "is cloned by",
                    "outward": "clones",
                },
                "outwardIssue": {
                    "id": "1",
                    "key": "CLONEIMP-1",
                    "fields": {"summary": "Source RFE"},
                },
            }
        ],
    )

    resp = await client.post(
        "/api/admin/import", json={"issues": [source, derived]}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    derived_resp = await client.get("/rest/api/2/issue/CLONEIMP-2", headers=AUTH)
    assert derived_resp.status_code == 200
    derived_links = derived_resp.json()["fields"]["issuelinks"]
    assert any(link.get("outwardIssue", {}).get("key") == "CLONEIMP-1" for link in derived_links)

    source_resp = await client.get("/rest/api/2/issue/CLONEIMP-1", headers=AUTH)
    assert source_resp.status_code == 200
    source_links = source_resp.json()["fields"]["issuelinks"]
    assert any(link.get("inwardIssue", {}).get("key") == "CLONEIMP-2" for link in source_links)


@pytest.mark.asyncio
async def test_api_import_jira_api_with_parent(client):
    """Parent/epic link from Jira REST API format is resolved."""
    parent = _jira_api_issue("PARTEST-1", "Parent Epic", issuetype="Epic")
    child = _jira_api_issue(
        "PARTEST-2", "Child Story",
        issuetype="Story",
        parent={"id": "1", "key": "PARTEST-1"},
    )

    resp = await client.post(
        "/api/admin/import", json={"issues": [parent, child]}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    child_resp = await client.get("/rest/api/2/issue/PARTEST-2", headers=AUTH)
    assert child_resp.status_code == 200
    parent_field = child_resp.json()["fields"]["parent"]
    assert parent_field is not None
    assert parent_field["key"] == "PARTEST-1"


@pytest.mark.asyncio
async def test_api_import_flat_format_still_works(client):
    """Existing flat format continues to work after Jira API format support."""
    issue = {
        "key": "FLAT-1",
        "summary": "Flat format issue",
        "status": "Open",
        "priority": "Minor",
        "issue_type": "Task",
        "reporter": "Flat Reporter",
        "project": {"key": "FLAT", "name": "Flat Project"},
        "labels": ["flat-test"],
        "components": [{"name": "Core"}],
        "affects_versions": [],
        "fix_versions": [],
    }

    resp = await client.post("/api/admin/import", json={"issues": [issue]}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1

    issue_resp = await client.get("/rest/api/2/issue/FLAT-1", headers=AUTH)
    assert issue_resp.status_code == 200
    fields = issue_resp.json()["fields"]
    assert fields["summary"] == "Flat format issue"
    assert fields["status"]["name"] == "Open"
    assert fields["issuetype"]["name"] == "Task"
    assert "flat-test" in fields["labels"]
