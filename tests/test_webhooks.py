"""Webhook registration and durable event capture tests."""

import httpx

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
