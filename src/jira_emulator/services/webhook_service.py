"""Webhook registration, matching, payload, and delivery helpers."""

import hashlib
import hmac
import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.config import get_settings
from jira_emulator.models.webhook import Webhook, WebhookOutbox

logger = logging.getLogger(__name__)


def _jql_matches(jql: str, fields: dict) -> bool:
    """Evaluate the small, useful webhook JQL subset without building SQL."""
    for clause in re.split(r"\s+AND\s+", jql, flags=re.IGNORECASE):
        match = re.match(r"\s*(project|status|issueKey|issuetype|priority)\s*(=|!=)\s*[\"']?([^\"']+?)[\"']?\s*$", clause, re.I)
        if not match:
            return False
        field, operator, expected = match.groups()
        actual = fields.get(field) or fields.get(field.lower())
        if isinstance(actual, dict):
            actual = actual.get("key") or actual.get("name") or actual.get("id")
        equal = str(actual).casefold() == expected.strip().casefold()
        if (operator == "=" and not equal) or (operator == "!=" and equal):
            return False
    return True

EVENTS = {
    "jira:issue_created", "jira:issue_updated", "jira:issue_deleted",
    "issue_property_set", "issue_property_deleted", "comment_created", "comment_updated",
    "comment_deleted", "attachment_created", "attachment_deleted", "issuelink_created",
    "issuelink_deleted", "project_created", "project_updated", "project_deleted",
    "project_soft_deleted", "project_restored_deleted", "project_archived",
    "project_restored_archived", "jira:version_released", "jira:version_unreleased",
    "jira:version_created", "jira:version_moved", "jira:version_updated", "jira:version_merged",
    "jira:version_deleted", "issuetype_created", "issuetype_updated", "issuetype_deleted",
    "user_created", "user_updated", "user_deleted", "worklog_created", "worklog_updated",
    "worklog_deleted", "sprint_created", "sprint_updated", "sprint_deleted", "sprint_started",
    "sprint_closed", "board_created", "board_updated", "board_deleted", "board_configuration_changed",
    "filter_created", "filter_updated", "filter_deleted", "app_access_to_objects_blocked",
    "app_access_to_objects_in_container_blocked", "jira_expression_evaluation_failed",
    "option_voting_changed", "option_watching_changed", "option_unassigned_issues_changed",
    "option_subtasks_changed", "option_issuelinks_changed", "option_timetracking_changed",
    "option_timetracking_provider_changed",
}
DYNAMIC_EVENTS = {
    "jira:issue_created", "jira:issue_updated", "jira:issue_deleted", "comment_created",
    "comment_updated", "comment_deleted", "issue_property_set", "issue_property_deleted",
    "sprint_created", "sprint_updated", "sprint_closed", "sprint_deleted", "sprint_started",
    "jira:version_released", "jira:version_unreleased", "jira:version_created", "jira:version_moved",
    "jira:version_updated", "jira:version_merged", "jira:version_deleted",
}


def _json(value, default=None):
    if value is None:
        return default
    return json.loads(value)


def _dump(value) -> str | None:
    return json.dumps(value, separators=(",", ":")) if value is not None else None


def _validate_url(url: str) -> None:
    settings = get_settings()
    parsed = urlparse(url)
    if parsed.scheme not in ({"https"} | ({"http"} if settings.WEBHOOK_ALLOW_INSECURE_HTTP else set())):
        raise ValueError("Webhook URL must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Webhook URL must include a hostname and no userinfo")
    if parsed.port and parsed.port == 80 and parsed.scheme == "https":
        raise ValueError("Webhook URL port 80 is not allowed")


def _substitute(url: str, context: dict) -> str:
    for key, value in context.items():
        url = url.replace("{" + key + "}", str(value))
    if "{" in url or "}" in url:
        raise ValueError("Webhook URL contains an unavailable variable")
    return url


def _admin_json(webhook: Webhook, base_url: str) -> dict:
    return {
        "name": webhook.name or "",
        "description": webhook.description or "",
        "url": webhook.url,
        "excludeBody": webhook.exclude_body,
        "verifySsl": webhook.verify_ssl,
        "events": _json(webhook.events, []),
        "filters": {"issue-related-events-section": webhook.jql_filter} if webhook.jql_filter else {},
        "enabled": webhook.enabled,
        "self": f"{base_url}/rest/webhooks/1.0/webhook/{webhook.id}",
        "lastUpdated": int((webhook.updated_at or webhook.created_at).timestamp() * 1000),
        "isSigned": webhook.secret is not None,
    }


def _dynamic_json(webhook: Webhook, base_url: str) -> dict:
    data = {
        "events": _json(webhook.events, []),
        "expirationDate": webhook.expires_at.strftime("%Y-%m-%dT%H:%M:%S.000+0000") if webhook.expires_at else None,
        "id": webhook.id,
        "jqlFilter": webhook.jql_filter or "",
        "url": webhook.url,
    }
    if webhook.field_ids_filter:
        data["fieldIdsFilter"] = _json(webhook.field_ids_filter, [])
    if webhook.issue_property_keys_filter:
        data["issuePropertyKeysFilter"] = _json(webhook.issue_property_keys_filter, [])
    return data


async def create_admin(db: AsyncSession, body: dict, project_id: int | None = None) -> Webhook:
    events = list(dict.fromkeys(body.get("events") or []))
    if not body.get("name") or not body.get("url") or not events:
        raise ValueError("name, url, and at least one event are required")
    unknown = [event for event in events if event not in EVENTS]
    if unknown:
        raise ValueError(f"Unsupported webhook event: {unknown[0]}")
    _validate_url(body["url"])
    filters = body.get("filters") or {}
    webhook = Webhook(kind="admin", project_id=project_id, name=body["name"], description=body.get("description"),
                      url=body["url"], events=_dump(events) or "[]",
                      jql_filter=filters.get("issue-related-events-section"),
                      exclude_body=bool(body.get("excludeBody", False)),
                      verify_ssl=bool(body.get("verifySsl", not body.get("allowInsecureSsl", False))),
                      secret=body.get("secret") or None,
                      enabled=bool(body.get("enabled", True)))
    if webhook.jql_filter:
        from jira_emulator.jql.parser import parse_jql
        parse_jql(webhook.jql_filter)
    db.add(webhook)
    await db.flush()
    return webhook


async def create_dynamic(db: AsyncSession, body: dict, owner_id: int) -> list[dict]:
    url = body.get("url")
    if not url:
        raise ValueError("url is required")
    _validate_url(url)
    entries = body.get("webhooks")
    if not isinstance(entries, list) or not entries:
        raise ValueError("webhooks must be a non-empty array")
    count = (await db.execute(select(Webhook).where(Webhook.kind == "dynamic", Webhook.owner_user_id == owner_id,
                                                      Webhook.enabled.is_(True)))).scalars().all()
    results = []
    for item in entries:
        errors = []
        events = list(dict.fromkeys(item.get("events") or []))
        errors.extend(f"Unsupported event {event}" for event in events if event not in DYNAMIC_EVENTS)
        if not events:
            errors.append("events is required")
        jql = item.get("jqlFilter") or ""
        if jql:
            try:
                from jira_emulator.jql.parser import parse_jql
                parse_jql(jql)
            except Exception as exc:
                errors.append(str(exc))
        if len(count) >= 5:
            errors.append("The dynamic webhook limit has been reached")
        if errors:
            results.append({"errors": errors})
            continue
        webhook = Webhook(kind="dynamic", owner_user_id=owner_id, url=url, events=_dump(events) or "[]",
                          jql_filter=jql, field_ids_filter=_dump(item.get("fieldIdsFilter")),
                          issue_property_keys_filter=_dump(item.get("issuePropertyKeysFilter")),
                          expires_at=datetime.utcnow() + timedelta(days=30))
        db.add(webhook)
        await db.flush()
        count.append(webhook)
        results.append({"createdWebhookId": webhook.id})
    return results


async def enqueue_event(db: AsyncSession, event: str, payload: dict, *, project_id: int | None = None,
                        issue_fields: dict | None = None, changed_fields: set[str] | None = None,
                        property_key: str | None = None, trace: str | None = None) -> int:
    if not get_settings().WEBHOOKS_ENABLED:
        return 0
    now = datetime.utcnow()
    registrations = (await db.execute(select(Webhook).where(Webhook.enabled.is_(True), Webhook.events.contains(event)))).scalars().all()
    grouped: dict[tuple[int | None, str, str], list[int]] = {}
    for webhook in registrations:
        if webhook.expires_at and webhook.expires_at < now:
            continue
        if webhook.project_id is not None and webhook.project_id != project_id:
            continue
        if webhook.jql_filter and issue_fields is not None:
            if not _jql_matches(webhook.jql_filter, issue_fields):
                continue
        fields = _json(webhook.field_ids_filter, []) or []
        if fields and not (set(fields) & (changed_fields or set())):
            continue
        keys = _json(webhook.issue_property_keys_filter, []) or []
        if keys and property_key not in keys:
            continue
        key = (webhook.owner_user_id if webhook.kind == "dynamic" else webhook.id, webhook.url, "dynamic" if webhook.kind == "dynamic" else str(webhook.id))
        grouped.setdefault(key, []).append(webhook.id)
    created = 0
    for _key, ids in grouped.items():
        first = next(w for w in registrations if w.id == ids[0])
        context = payload.get("urlContext", {})
        url = _substitute(first.url, context)
        body = dict(payload)
        body.pop("urlContext", None)
        if first.kind == "dynamic":
            body["matchedWebhookIds"] = sorted(ids)
        serialized = "" if first.exclude_body else json.dumps(body, separators=(",", ":"), default=str)
        outbox = WebhookOutbox(id=str(uuid.uuid4()), webhook_id=first.id, owner_user_id=first.owner_user_id,
                               url=url, event=event, payload=serialized, secret=first.secret,
                               verify_ssl=first.verify_ssl,
                               next_attempt_at=now)
        db.add(outbox)
        created += 1
    return created


def signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def deliver_once(row: WebhookOutbox) -> tuple[bool, int | None, str | None]:
    body = row.payload.encode()
    headers = {"Content-Type": "application/json", "User-Agent": "jira-emulator/0.1.0",
               "X-Atlassian-Webhook-Identifier": row.id, "X-Atlassian-Webhook-Flow": row.flow}
    if row.attempt_count:
        headers["X-Atlassian-Webhook-Retry"] = str(row.attempt_count)
    if row.secret:
        headers["X-Hub-Signature"] = signature(row.secret, body)
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=5,
            verify=row.verify_ssl,
            timeout=httpx.Timeout(
                get_settings().WEBHOOK_TOTAL_TIMEOUT_SECONDS,
                connect=get_settings().WEBHOOK_CONNECT_TIMEOUT_SECONDS,
            ),
        ) as client:
            response = await client.post(row.url, content=body, headers=headers)
        if 200 <= response.status_code < 300:
            return True, response.status_code, None
        retryable = response.status_code in {408, 409, 425, 429} or response.status_code >= 500
        return False, response.status_code, ("retryable HTTP failure" if retryable else "permanent HTTP failure")
    except Exception as exc:
        return False, None, str(exc)[:500]


async def claim_due(db: AsyncSession, limit: int = 20) -> list[WebhookOutbox]:
    rows = (await db.execute(select(WebhookOutbox).where(WebhookOutbox.state == "pending",
        WebhookOutbox.next_attempt_at <= datetime.utcnow()).order_by(WebhookOutbox.next_attempt_at).limit(limit))).scalars().all()
    for row in rows:
        row.state = "delivering"
        row.attempt_count += 1
    await db.commit()
    return rows
