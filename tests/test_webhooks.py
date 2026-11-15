"""Webhook registration and durable event capture tests."""

import httpx
import pytest

from tests.conftest import AUTH_HEADER


async def test_admin_webhook_lifecycle(client: httpx.AsyncClient):
    created = await client.post(
        "/rest/webhooks/1.0/webhook",
        json={
            "name": "Demo",
            "url": "https://example.test/hook",
            "events": ["jira:issue_created"],
            "secret": "top-secret",
        },
        headers=AUTH_HEADER,
    )
    assert created.status_code == 201
    data = created.json()
    assert data["isSigned"] is True
    assert data["verifySsl"] is True
    assert "secret" not in data
    webhook_id = int(data["self"].rsplit("/", 1)[1])

    listed = await client.get("/rest/webhooks/1.0/webhook", headers=AUTH_HEADER)
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "Demo"

    updated = await client.put(
        f"/rest/webhooks/1.0/webhook/{webhook_id}",
        json={"name": "Updated", "url": "https://example.test/new", "events": ["jira:issue_updated"]},
        headers=AUTH_HEADER,
    )
    assert updated.status_code == 200
    assert updated.json()["isSigned"] is True  # omitted secret preserves it

    insecure = await client.post(
        "/rest/webhooks/1.0/webhook",
        json={
            "name": "Local",
            "url": "https://example.test/local",
            "events": ["jira:issue_created"],
            "allowInsecureSsl": True,
        },
        headers=AUTH_HEADER,
    )
    assert insecure.status_code == 201
    assert insecure.json()["verifySsl"] is False

    deleted = await client.delete(f"/rest/webhooks/1.0/webhook/{webhook_id}", headers=AUTH_HEADER)
    assert deleted.status_code == 204


async def test_dynamic_webhook_v3_registration_and_refresh(client: httpx.AsyncClient):
    registered = await client.post(
        "/rest/api/3/webhook",
        json={
            "url": "https://example.test/hook",
            "webhooks": [
                {"jqlFilter": "project = RHOAIENG", "events": ["jira:issue_created"]},
            ],
        },
        headers=AUTH_HEADER,
    )
    assert registered.status_code == 200
    webhook_id = registered.json()["webhookRegistrationResult"][0]["createdWebhookId"]

    listed = await client.get("/rest/api/2/webhook", headers=AUTH_HEADER)
    assert listed.json()["values"][0]["id"] == webhook_id

    refreshed = await client.put("/rest/api/3/webhook/refresh", json={"webhookIds": [webhook_id]}, headers=AUTH_HEADER)
    assert refreshed.status_code == 200
    assert "expirationDate" in refreshed.json()

    removed = await client.request(
        "DELETE", "/rest/api/3/webhook", json={"webhookIds": [webhook_id]}, headers=AUTH_HEADER
    )
    assert removed.status_code == 202


async def test_issue_creation_enqueues_matching_webhook(client: httpx.AsyncClient):
    await client.post(
        "/rest/webhooks/1.0/webhook",
        json={"name": "Demo", "url": "https://example.test/{issue.key}", "events": ["jira:issue_created"]},
        headers=AUTH_HEADER,
    )
    response = await client.post(
        "/rest/api/2/issue",
        json={"fields": {"project": {"key": "RHOAIENG"}, "issuetype": {"name": "Bug"}, "summary": "Webhook test"}},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201
    from sqlalchemy import select

    from jira_emulator.database import get_session_factory
    from jira_emulator.models.webhook import WebhookOutbox

    async with get_session_factory()() as db:
        rows = (await db.execute(select(WebhookOutbox))).scalars().all()
        assert len(rows) == 1
        assert rows[0].url.endswith(response.json()["key"])
        assert '"webhookEvent":"jira:issue_created"' in rows[0].payload


@pytest.mark.parametrize("v", [2, 3])
async def test_issuelink_webhooks_use_jira_source_destination_shape(client: httpx.AsyncClient, v: int):
    """issuelink_* payloads match Jira: source "clones" destination."""
    import json

    from sqlalchemy import select

    from jira_emulator.database import get_session_factory
    from jira_emulator.models.webhook import WebhookOutbox

    await client.post(
        "/rest/webhooks/1.0/webhook",
        json={
            "name": "Links",
            "url": "https://example.test/{sourceIssue.key}/{destinationIssue.key}",
            "events": ["issuelink_created", "issuelink_deleted"],
        },
        headers=AUTH_HEADER,
    )

    async def create(project: str, issuetype: str) -> dict:
        resp = await client.post(
            "/rest/api/2/issue",
            json={"fields": {"project": {"key": project}, "issuetype": {"name": issuetype}, "summary": project}},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 201
        return resp.json()

    rfe = await create("RHAIRFE", "Feature Request")
    strat = await create("RHAISTRAT", "Feature")
    # strat-creator's payload: RHAISTRAT clones RHAIRFE.
    resp = await client.post(
        f"/rest/api/{v}/issueLink",
        json={"type": {"name": "Cloners"}, "inwardIssue": {"key": strat["key"]}, "outwardIssue": {"key": rfe["key"]}},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    links = (await client.get(f"/rest/api/{v}/issue/{strat['key']}", headers=AUTH_HEADER)).json()["fields"][
        "issuelinks"
    ]
    assert links[0]["outwardIssue"]["key"] == rfe["key"]  # GET: STRAT "clones" RFE
    link_id = links[0]["id"]
    assert (await client.delete(f"/rest/api/{v}/issueLink/{link_id}", headers=AUTH_HEADER)).status_code == 204

    async with get_session_factory()() as db:
        rows = (await db.execute(select(WebhookOutbox).order_by(WebhookOutbox.created_at))).scalars().all()
    by_event = {row.event: row for row in rows}
    assert set(by_event) == {"issuelink_created", "issuelink_deleted"}

    expected_link = {
        "id": int(link_id),
        "sourceIssueId": int(strat["id"]),
        "destinationIssueId": int(rfe["id"]),
        "issueLinkType": {
            "id": int(links[0]["type"]["id"]),
            "name": "Cloners",
            "outwardName": "clones",
            "inwardName": "is cloned by",
            "style": None,
            "isSubTaskLinkType": False,
            "isSystemLinkType": False,
        },
        "systemLink": False,
    }
    for event, row in by_event.items():
        body = json.loads(row.payload)
        assert body["webhookEvent"] == event
        assert body["issueLink"] == expected_link
        assert "urlContext" not in body
        assert row.url == f"https://example.test/{strat['key']}/{rfe['key']}"
