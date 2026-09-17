"""Jira webhook registration APIs."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.user import User
from jira_emulator.models.webhook import Webhook, WebhookOutbox
from jira_emulator.services import webhook_service

api_router = APIRouter(prefix="/rest/api/2")
admin_router = APIRouter(prefix="/rest/webhooks/1.0")


@api_router.post("/webhook")
async def register_dynamic(body: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    results = await webhook_service.create_dynamic(db, body, current_user.id)
    return {"webhookRegistrationResult": results}


@api_router.get("/webhook")
async def list_dynamic(startAt: int = Query(0, ge=0), maxResults: int = Query(100, ge=1, le=100),
                       current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Webhook).where(Webhook.kind == "dynamic", Webhook.owner_user_id == current_user.id)
                             .order_by(Webhook.id))).scalars().all()
    values = [webhook_service._dynamic_json(row, get_settings().BASE_URL) for row in rows]
    return {"startAt": startAt, "maxResults": maxResults, "total": len(values),
            "isLast": startAt + maxResults >= len(values), "values": values[startAt:startAt + maxResults]}


@api_router.delete("/webhook", status_code=202)
async def delete_dynamic(body: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ids = body.get("webhookIds") or []
    if not isinstance(ids, list):
        raise ValueError("webhookIds must be an array")
    rows = (await db.execute(select(Webhook).where(Webhook.id.in_(ids), Webhook.kind == "dynamic",
                                                      Webhook.owner_user_id == current_user.id))).scalars().all()
    for row in rows:
        await db.delete(row)
    return Response(status_code=202)


@api_router.put("/webhook/refresh")
async def refresh_dynamic(body: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ids = body.get("webhookIds") or []
    rows = (await db.execute(select(Webhook).where(Webhook.id.in_(ids), Webhook.kind == "dynamic",
                                                      Webhook.owner_user_id == current_user.id))).scalars().all()
    expiration = __import__("datetime").datetime.utcnow() + __import__("datetime").timedelta(days=30)
    for row in rows:
        row.expires_at = expiration
    return {"expirationDate": expiration.strftime("%Y-%m-%dT%H:%M:%S.000+0000")}


@api_router.get("/webhook/failed")
async def failed_dynamic(maxResults: int = Query(100, ge=1, le=100), after: int = Query(0, ge=0),
                         current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WebhookOutbox).where(WebhookOutbox.owner_user_id == current_user.id,
        WebhookOutbox.state == "failed").order_by(WebhookOutbox.failed_at).limit(maxResults + 1))).scalars().all()
    rows = [row for row in rows if int((row.failed_at or row.created_at).timestamp() * 1000) > after]
    values = [{"id": row.id, "body": row.payload, "url": row.url,
               "failureTime": int((row.failed_at or row.created_at).timestamp() * 1000)} for row in rows[:maxResults]]
    result = {"values": values, "maxResults": maxResults}
    if len(rows) > maxResults and values:
        result["next"] = f"{get_settings().BASE_URL}/rest/api/2/webhook/failed?after={values[-1]['failureTime']}&maxResults={maxResults}"
    return result


@admin_router.post("/webhook", status_code=201)
async def create_admin_webhook(body: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await webhook_service.create_admin(db, body)
    return webhook_service._admin_json(row, get_settings().BASE_URL)


@admin_router.get("/webhook")
async def list_admin_webhooks(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Webhook).where(Webhook.kind == "admin").order_by(Webhook.id))).scalars().all()
    return [webhook_service._admin_json(row, get_settings().BASE_URL) for row in rows]


@admin_router.get("/webhook/{webhook_id}")
async def get_admin_webhook(webhook_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(Webhook, webhook_id)
    if row is None or row.kind != "admin":
        raise ValueError(f"Webhook {webhook_id} not found")
    return webhook_service._admin_json(row, get_settings().BASE_URL)


@admin_router.put("/webhook/{webhook_id}")
async def update_admin_webhook(webhook_id: int, body: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(Webhook, webhook_id)
    if row is None or row.kind != "admin":
        raise ValueError(f"Webhook {webhook_id} not found")
    secret_present = "secret" in body
    body.setdefault("verifySsl", row.verify_ssl)
    replacement = await webhook_service.create_admin(db, body)
    for field in ("name", "description", "url", "events", "jql_filter", "exclude_body", "verify_ssl", "enabled"):
        setattr(row, field, getattr(replacement, field))
    if secret_present:
        row.secret = body.get("secret") or None
    await db.delete(replacement)
    await db.flush()
    return webhook_service._admin_json(row, get_settings().BASE_URL)


@admin_router.delete("/webhook/{webhook_id}", status_code=204)
async def delete_admin_webhook(webhook_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(Webhook, webhook_id)
    if row is None or row.kind != "admin":
        raise ValueError(f"Webhook {webhook_id} not found")
    await db.delete(row)
    return Response(status_code=204)
