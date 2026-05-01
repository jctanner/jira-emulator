import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


async def _create_issue(client, project="RHOAIENG", summary="Test", **extra_fields):
    fields = {"project": {"key": project}, "summary": summary,
              "issuetype": {"name": "Bug"}}
    fields.update(extra_fields)
    resp = await client.post("/rest/api/2/issue", json={"fields": fields},
                             headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_issue_with_unknown_custom_field_string(client):
    """Creating an issue with an unknown customfield_* auto-creates the field."""
    issue = await _create_issue(client, summary="CF auto-create",
                                customfield_99999="hello")
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    fields = resp.json()["fields"]
    assert fields["customfield_99999"] == "hello"


@pytest.mark.asyncio
async def test_create_issue_with_unknown_custom_field_json(client):
    """An ADF dict value is stored as JSON and returned as a dict."""
    adf = {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [
            {"type": "inlineCard", "attrs": {
                "url": "https://github.com/org/repo/pull/42"}}
        ]}
    ]}
    issue = await _create_issue(client, summary="CF ADF",
                                customfield_88888=adf)
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    fields = resp.json()["fields"]
    cf_value = fields["customfield_88888"]
    assert isinstance(cf_value, dict)
    assert cf_value["type"] == "doc"


@pytest.mark.asyncio
async def test_update_issue_with_unknown_custom_field(client):
    """PUT with an unknown customfield_* auto-creates and stores the value."""
    issue = await _create_issue(client, summary="CF update test")

    resp = await client.put(
        f"/rest/api/2/issue/{issue['key']}",
        json={"fields": {"customfield_77777": "updated-value"}},
        headers=AUTH,
    )
    assert resp.status_code == 204

    resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    assert resp.json()["fields"]["customfield_77777"] == "updated-value"


@pytest.mark.asyncio
async def test_import_with_raw_customfield_key(client):
    """Admin import with a raw customfield_* key stores the value."""
    adf = {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [
            {"type": "inlineCard", "attrs": {
                "url": "https://github.com/org/repo/pull/55"}}
        ]}
    ]}
    resp = await client.post("/api/admin/import", json={"issues": [{
        "key": "TEST-500",
        "summary": "Import with raw customfield",
        "project": "TEST",
        "issue_type": "Story",
        "description": "Test",
        "customfield_10875": adf,
    }]}, headers=AUTH)
    assert resp.status_code == 200

    resp = await client.get("/rest/api/2/issue/TEST-500", headers=AUTH)
    cf_value = resp.json()["fields"]["customfield_10875"]
    assert isinstance(cf_value, dict)
    assert cf_value["type"] == "doc"


@pytest.mark.asyncio
async def test_create_issue_with_number_custom_field(client):
    """A numeric custom field value is stored and returned correctly."""
    issue = await _create_issue(client, summary="CF number",
                                customfield_66666=42.5)
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    assert resp.json()["fields"]["customfield_66666"] == 42.5
