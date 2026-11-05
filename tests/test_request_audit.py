"""Tests for the request audit (GET/DELETE /api/admin/requests)."""

import json

import pytest

from tests.conftest import AUTH_HEADER


async def _create_issue(client, api="2", summary="Audited"):
    resp = await client.post(
        f"/rest/api/{api}/issue",
        json={"fields": {"project": {"key": "RHOAIENG"}, "summary": summary, "issuetype": {"name": "Bug"}}},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    return resp.json()["key"]


async def _audit(client, **params):
    resp = await client.get("/api/admin/requests", params=params, headers=AUTH_HEADER)
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.parametrize("api", ["2", "3"])
async def test_records_writes_with_client_path_and_body(client, api):
    key = await _create_issue(client, api=api)
    update = {"update": {"labels": [{"add": "strat-creator-auto-created"}]}}
    resp = await client.put(f"/rest/api/{api}/issue/{key}?notifyUsers=false", json=update, headers=AUTH_HEADER)
    assert resp.status_code == 204
    await client.get(f"/rest/api/{api}/issue/{key}", headers=AUTH_HEADER)

    entries = (await _audit(client))["requests"]

    assert [(e["method"], e["path"], e["status"]) for e in entries] == [
        ("POST", f"/rest/api/{api}/issue", 201),
        ("PUT", f"/rest/api/{api}/issue/{key}", 204),
    ]
    put = entries[1]
    assert put["query"] == "notifyUsers=false"
    assert put["user"] == "admin"
    assert json.loads(put["body"]) == update
    assert put["body_truncated"] is False


async def test_admin_and_read_requests_not_recorded(client):
    await client.post("/api/admin/snapshots", json={}, headers=AUTH_HEADER)
    await client.post("/rest/api/2/search", json={"jql": "project = RHOAIENG"}, headers=AUTH_HEADER)

    entries = (await _audit(client))["requests"]

    # Search is a POST, so it is recorded; the admin call is not.
    assert [e["path"] for e in entries] == ["/rest/api/2/search"]


async def test_since_and_clear(client):
    await _create_issue(client, summary="first")
    first = await _audit(client)
    await _create_issue(client, summary="second")

    newer = await _audit(client, since=first["last_seq"])
    assert len(newer["requests"]) == 1
    assert "second" in newer["requests"][0]["body"]

    assert (await client.delete("/api/admin/requests", headers=AUTH_HEADER)).status_code == 204
    cleared = await _audit(client)
    assert cleared["requests"] == []
    assert cleared["last_seq"] == newer["last_seq"]

    await _create_issue(client, summary="third")
    assert [e["seq"] for e in (await _audit(client))["requests"]] == [newer["last_seq"] + 1]


async def test_body_capped(client):
    client_app = client._transport.app
    client_app.state.request_audit.max_body_bytes = 10
    await _create_issue(client)

    entry = (await _audit(client))["requests"][0]

    assert entry["body_truncated"] is True
    assert len(entry["body"]) == 10
    assert entry["body_bytes"] > 10


async def test_attachment_upload_recorded(client):
    key = await _create_issue(client)
    files = {"file": ("RHAISTRAT-1-strategy.md", b"# Strategy", "text/markdown")}
    resp = await client.post(
        f"/rest/api/3/issue/{key}/attachments", files=files, headers={**AUTH_HEADER, "X-Atlassian-Token": "no-check"}
    )
    assert resp.status_code == 200

    entry = (await _audit(client))["requests"][-1]

    assert entry["path"] == f"/rest/api/3/issue/{key}/attachments"
    assert entry["content_type"].startswith("multipart/form-data")
    assert 'filename="RHAISTRAT-1-strategy.md"' in entry["body"]
    assert "# Strategy" in entry["body"]
