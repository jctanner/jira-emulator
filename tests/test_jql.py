import pytest
from jira_emulator.jql.parser import parse_jql
from jira_emulator.jql.transformer import JQLTransformer

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}

async def _create_issue(client, project="RHOAIENG", summary="Test", issuetype="Bug", **extra_fields):
    fields = {"project": {"key": project}, "summary": summary, "issuetype": {"name": issuetype}}
    fields.update(extra_fields)
    resp = await client.post("/rest/api/2/issue", json={"fields": fields}, headers=AUTH)
    return resp.json()

# -- Parser unit tests (no DB needed) --

def test_parse_simple_equality():
    """Parse 'project = DEMO'."""
    tree = parse_jql("project = DEMO")
    assert tree is not None

def test_parse_and_or():
    """Parse compound query with AND/OR."""
    tree = parse_jql("project = A AND status = Open OR priority = High")
    assert tree is not None

def test_parse_in_clause():
    """Parse IN clause."""
    tree = parse_jql('status IN ("Open", "In Progress")')
    assert tree is not None

def test_parse_not_in_clause():
    """Parse NOT IN clause."""
    tree = parse_jql('status NOT IN ("Closed", "Done")')
    assert tree is not None

def test_parse_is_empty():
    """Parse IS EMPTY."""
    tree = parse_jql("resolution IS EMPTY")
    assert tree is not None

def test_parse_order_by():
    """Parse ORDER BY."""
    tree = parse_jql("project = DEMO ORDER BY created DESC")
    assert tree is not None

def test_parse_function_call():
    """Parse function call currentUser()."""
    tree = parse_jql("assignee = currentUser()")
    assert tree is not None

def test_parse_contains_operator():
    """Parse ~ operator."""
    tree = parse_jql('summary ~ "test text"')
    assert tree is not None

# -- Integration tests (need DB via client fixture) --

@pytest.mark.asyncio
async def test_search_by_status(client):
    """Search with status filter returns matching issues."""
    await _create_issue(client, summary="Status test")
    resp = await client.post("/rest/api/2/search", json={
        "jql": 'project = RHOAIENG AND status = "New"',
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    for issue in data["issues"]:
        assert issue["fields"]["status"]["name"] == "New"

@pytest.mark.asyncio
async def test_search_by_issuetype(client):
    """Search with issuetype filter."""
    await _create_issue(client, summary="Bug test", issuetype="Bug")
    await _create_issue(client, summary="Story test", issuetype="Story")

    resp = await client.post("/rest/api/2/search", json={
        "jql": 'project = RHOAIENG AND issuetype = Bug',
        "maxResults": 50,
    }, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    for issue in data["issues"]:
        assert issue["fields"]["issuetype"]["name"] == "Bug"
