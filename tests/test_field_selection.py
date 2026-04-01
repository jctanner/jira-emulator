import pytest
import httpx

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}

async def _create_issue(client, project="RHOAIENG", summary="Test", issuetype="Bug"):
    resp = await client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": project}, "summary": summary, "issuetype": {"name": issuetype}}
    }, headers=AUTH)
    return resp.json()

@pytest.mark.asyncio
async def test_search_with_field_selection(client):
    """Search with fields parameter returns only selected fields."""
    await _create_issue(client, summary="Field selection test")
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = RHOAIENG",
        "fields": ["summary", "status"],
        "maxResults": 10,
    }, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    for issue in data["issues"]:
        fields = issue["fields"]
        assert "summary" in fields
        assert "status" in fields
        # These should NOT be present
        assert "description" not in fields
        assert "priority" not in fields

@pytest.mark.asyncio
async def test_search_with_all_fields(client):
    """Search with fields=["*all"] returns all fields."""
    await _create_issue(client, summary="All fields test")
    resp = await client.post("/rest/api/2/search", json={
        "jql": "project = RHOAIENG",
        "fields": ["*all"],
        "maxResults": 10,
    }, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    for issue in data["issues"]:
        fields = issue["fields"]
        assert "summary" in fields
        assert "status" in fields
        assert "description" in fields

@pytest.mark.asyncio
async def test_search_get_with_fields_param(client):
    """GET /search?fields=summary,status limits fields."""
    await _create_issue(client, summary="GET fields test")
    resp = await client.get(
        "/rest/api/2/search?jql=project+%3D+RHOAIENG&fields=summary,status",
        headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    for issue in data["issues"]:
        fields = issue["fields"]
        assert "summary" in fields
        assert "status" in fields
        assert "priority" not in fields
