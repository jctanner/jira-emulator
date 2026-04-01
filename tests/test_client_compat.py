"""Client compatibility tests — mirrors assistant_mcp call patterns."""

import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


@pytest.mark.asyncio
async def test_full_workflow(client):
    """End-to-end workflow matching assistant_mcp usage patterns.

    Steps: auth check -> search -> create issue -> get issue -> update issue ->
    add comment -> transition -> add link -> add watcher -> search again -> delete
    """
    # 1. Auth check — GET /rest/api/2/myself
    resp = await client.get("/rest/api/2/myself", headers=AUTH)
    assert resp.status_code == 200
    myself = resp.json()
    assert "name" in myself
    assert "displayName" in myself
    assert "emailAddress" in myself
    current_user = myself["name"]

    # 2. List projects — GET /rest/api/2/project
    resp = await client.get("/rest/api/2/project", headers=AUTH)
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) >= 4
    project_keys = [p["key"] for p in projects]
    assert "RHOAIENG" in project_keys

    # 3. Search for existing issues (empty project) — POST /rest/api/2/search
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = RHOAIENG ORDER BY created DESC",
        "startAt": 0,
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200
    search_result = resp.json()
    assert "total" in search_result
    assert "issues" in search_result
    assert "startAt" in search_result
    assert "maxResults" in search_result
    initial_count = search_result["total"]

    # 4. Create an issue — POST /rest/api/2/issue
    resp = await client.post("/rest/api/2/issue", json={
        "fields": {
            "project": {"key": "RHOAIENG"},
            "summary": "Client compat test issue",
            "description": "Created by client compatibility test",
            "issuetype": {"name": "Bug"},
            "priority": {"name": "Major"},
            "labels": ["compat-test", "automated"],
        }
    }, headers=AUTH)
    assert resp.status_code == 201
    created = resp.json()
    assert "id" in created
    assert "key" in created
    issue_key = created["key"]
    assert issue_key.startswith("RHOAIENG-")

    # 5. Get the created issue — GET /rest/api/2/issue/{key}
    resp = await client.get(f"/rest/api/2/issue/{issue_key}", headers=AUTH)
    assert resp.status_code == 200
    issue = resp.json()
    # Verify response structure matches what assistant_mcp expects
    assert "id" in issue
    assert "key" in issue
    assert "self" in issue
    fields = issue["fields"]
    assert fields["summary"] == "Client compat test issue"
    assert fields["description"] == "Created by client compatibility test"
    assert fields["status"]["name"] is not None
    assert fields["issuetype"]["name"] == "Bug"
    assert fields["priority"]["name"] == "Major"
    assert fields["project"]["key"] == "RHOAIENG"
    assert "compat-test" in fields["labels"]
    assert fields["reporter"] is not None
    assert "comment" in fields
    assert "comments" in fields["comment"]
    assert "issuelinks" in fields
    assert "components" in fields
    assert "fixVersions" in fields
    assert "created" in fields
    assert "updated" in fields

    # 6. Create a second issue for linking
    resp = await client.post("/rest/api/2/issue", json={
        "fields": {
            "project": {"key": "RHOAIENG"},
            "summary": "Related issue for linking",
            "issuetype": {"name": "Story"},
        }
    }, headers=AUTH)
    assert resp.status_code == 201
    related_key = resp.json()["key"]

    # 7. Update the issue — PUT /rest/api/2/issue/{key}
    resp = await client.put(f"/rest/api/2/issue/{issue_key}", json={
        "fields": {
            "summary": "Updated client compat test issue",
        },
        "update": {
            "labels": [{"add": "updated"}],
            "comment": [{"add": {"body": "Comment via update dict"}}],
        }
    }, headers=AUTH)
    assert resp.status_code == 204

    # Verify the update
    resp = await client.get(f"/rest/api/2/issue/{issue_key}", headers=AUTH)
    fields = resp.json()["fields"]
    assert fields["summary"] == "Updated client compat test issue"
    assert "updated" in fields["labels"]

    # 8. Add a comment — POST /rest/api/2/issue/{key}/comment
    resp = await client.post(f"/rest/api/2/issue/{issue_key}/comment", json={
        "body": "This is a standalone comment"
    }, headers=AUTH)
    assert resp.status_code == 201
    comment = resp.json()
    assert comment["body"] == "This is a standalone comment"
    assert "id" in comment
    assert "author" in comment
    assert "created" in comment

    # List comments
    resp = await client.get(f"/rest/api/2/issue/{issue_key}/comment", headers=AUTH)
    assert resp.status_code == 200
    comments_data = resp.json()
    assert "comments" in comments_data
    assert "total" in comments_data
    assert comments_data["total"] >= 2  # update comment + standalone

    # 9. Get transitions — GET /rest/api/2/issue/{key}/transitions
    resp = await client.get(f"/rest/api/2/issue/{issue_key}/transitions", headers=AUTH)
    assert resp.status_code == 200
    transitions = resp.json()
    assert "transitions" in transitions
    assert len(transitions["transitions"]) >= 1
    t = transitions["transitions"][0]
    assert "id" in t
    assert "name" in t
    assert "to" in t
    assert "name" in t["to"]
    assert "statusCategory" in t["to"]

    # 10. Perform transition — POST /rest/api/2/issue/{key}/transitions
    transition_id = transitions["transitions"][0]["id"]
    resp = await client.post(f"/rest/api/2/issue/{issue_key}/transitions", json={
        "transition": {"id": transition_id}
    }, headers=AUTH)
    assert resp.status_code == 204

    # 11. Create issue link — POST /rest/api/2/issueLink
    resp = await client.post("/rest/api/2/issueLink", json={
        "type": {"name": "Blocks"},
        "inwardIssue": {"key": issue_key},
        "outwardIssue": {"key": related_key},
    }, headers=AUTH)
    assert resp.status_code == 201

    # Verify link appears in issue response
    resp = await client.get(f"/rest/api/2/issue/{issue_key}", headers=AUTH)
    links = resp.json()["fields"]["issuelinks"]
    assert len(links) >= 1

    # 12. Add watcher — POST /rest/api/2/issue/{key}/watchers
    resp = await client.post(
        f"/rest/api/2/issue/{issue_key}/watchers",
        content=f'"{current_user}"',
        headers={**AUTH, "Content-Type": "application/json"},
    )
    assert resp.status_code == 204

    # Get watchers
    resp = await client.get(f"/rest/api/2/issue/{issue_key}/watchers", headers=AUTH)
    assert resp.status_code == 200
    watchers = resp.json()
    assert watchers["watchCount"] >= 1

    # 13. Search with filters — verify new issue appears
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = RHOAIENG ORDER BY created DESC",
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.json()["total"] == initial_count + 2  # original + related

    # 14. Search with field selection
    resp = await client.post("/rest/api/2/search", json={
        "jql": f"key = {issue_key}",
        "fields": ["summary", "status", "assignee"],
        "maxResults": 1,
    }, headers=AUTH)
    assert resp.status_code == 200
    limited = resp.json()["issues"][0]["fields"]
    assert "summary" in limited
    assert "status" in limited
    assert "description" not in limited  # should be filtered out

    # 15. Delete issue — DELETE /rest/api/2/issue/{key}
    resp = await client.delete(f"/rest/api/2/issue/{issue_key}", headers=AUTH)
    assert resp.status_code == 204

    # Verify deleted
    resp = await client.get(f"/rest/api/2/issue/{issue_key}", headers=AUTH)
    assert resp.status_code == 404

    # Clean up related issue
    await client.delete(f"/rest/api/2/issue/{related_key}", headers=AUTH)


@pytest.mark.asyncio
async def test_metadata_endpoints_structure(client):
    """Verify all metadata endpoints return the structure assistant_mcp expects."""
    # Priorities
    resp = await client.get("/rest/api/2/priority", headers=AUTH)
    assert resp.status_code == 200
    for p in resp.json():
        assert "id" in p
        assert "name" in p
        assert "self" in p

    # Statuses
    resp = await client.get("/rest/api/2/status", headers=AUTH)
    assert resp.status_code == 200
    for s in resp.json():
        assert "id" in s
        assert "name" in s
        assert "statusCategory" in s

    # Resolutions
    resp = await client.get("/rest/api/2/resolution", headers=AUTH)
    assert resp.status_code == 200
    for r in resp.json():
        assert "id" in r
        assert "name" in r

    # Issue types
    resp = await client.get("/rest/api/2/issuetype", headers=AUTH)
    assert resp.status_code == 200
    for t in resp.json():
        assert "id" in t
        assert "name" in t
        assert "subtask" in t

    # Fields
    resp = await client.get("/rest/api/2/field", headers=AUTH)
    assert resp.status_code == 200
    fields = resp.json()
    assert len(fields) > 0
    field_ids = [f["id"] for f in fields]
    assert "summary" in field_ids
    assert "status" in field_ids

    # Link types
    resp = await client.get("/rest/api/2/issueLinkType", headers=AUTH)
    assert resp.status_code == 200
    assert "issueLinkTypes" in resp.json()


@pytest.mark.asyncio
async def test_jql_patterns_used_by_client(client):
    """Test the specific JQL patterns that assistant_mcp tools generate."""
    # Create some test issues
    for i in range(3):
        await client.post("/rest/api/2/issue", json={
            "fields": {
                "project": {"key": "RHOAIENG"},
                "summary": f"JQL pattern test {i}",
                "issuetype": {"name": "Bug"},
                "priority": {"name": "Major"},
                "labels": ["jql-test"],
            }
        }, headers=AUTH)

    # Pattern 1: project = KEY ORDER BY created DESC
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = RHOAIENG ORDER BY created DESC",
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 3

    # Pattern 2: project = KEY AND status = "Name"
    resp = await client.post("/rest/api/2/search", json={
        "jql": 'project = RHOAIENG AND status = "New"',
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200

    # Pattern 3: project = KEY AND issuetype = Name
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = RHOAIENG AND issuetype = Bug",
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200

    # Pattern 4: labels = value
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = RHOAIENG AND labels = jql-test",
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 3

    # Pattern 5: resolution = Unresolved
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = RHOAIENG AND resolution = Unresolved",
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200

    # Pattern 6: summary ~ "text"
    resp = await client.post("/rest/api/2/search", json={
        "jql": 'project = RHOAIENG AND summary ~ "pattern test"',
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 3

    # Pattern 7: key = ISSUE-KEY
    resp = await client.post("/rest/api/2/search", json={
        "jql": "key = RHOAIENG-1",
        "maxResults": 1,
    }, headers=AUTH)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_session_auth_flow(client):
    """Test the session authentication flow used by assistant_mcp."""
    # Login
    resp = await client.post("/rest/auth/1/session", json={
        "username": "admin",
        "password": "admin",
    })
    assert resp.status_code == 200
    session_data = resp.json()
    assert "session" in session_data
    assert "name" in session_data["session"]
    assert session_data["session"]["name"] == "JSESSIONID"

    # Get session info
    resp = await client.get("/rest/auth/1/session", headers=AUTH)
    assert resp.status_code == 200
    assert "name" in resp.json()

    # Delete session (logout)
    resp = await client.delete("/rest/auth/1/session", headers=AUTH)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_token_auth_flow(client):
    """Test the PAT authentication flow."""
    # Create token
    resp = await client.post("/rest/pat/latest/tokens", json={
        "name": "Compat Test Token",
    }, headers=AUTH)
    assert resp.status_code == 201
    token_data = resp.json()
    assert "rawToken" in token_data
    assert "id" in token_data

    # List tokens
    resp = await client.get("/rest/pat/latest/tokens", headers=AUTH)
    assert resp.status_code == 200
    tokens = resp.json()
    assert len(tokens) >= 1
    for t in tokens:
        assert "rawToken" not in t  # raw token should not be exposed in list
        assert "id" in t
        assert "name" in t

    # Revoke token
    token_id = token_data["id"]
    resp = await client.delete(f"/rest/pat/latest/tokens/{token_id}", headers=AUTH)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_user_management_flow(client):
    """Test user CRUD as used by assistant_mcp."""
    # Create user
    resp = await client.post("/rest/api/2/user", json={
        "name": "compat_test_user",
        "displayName": "Compat Test User",
        "emailAddress": "compat@example.com",
        "password": "testpass123",
    }, headers=AUTH)
    assert resp.status_code == 201
    user = resp.json()
    assert user["name"] == "compat_test_user"

    # Search assignable users
    resp = await client.get(
        "/rest/api/2/user/assignable/search?project=RHOAIENG",
        headers=AUTH,
    )
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) >= 1
