"""Remote link endpoints: /rest/api/2/issue/{key}/remotelink."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.database import get_db
from jira_emulator.models.remote_link import RemoteLink
from jira_emulator.models.user import User
from jira_emulator.services import issue_service

router = APIRouter(prefix="/rest/api/2")


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


def _link_response(link: RemoteLink, request: Request, issue_key: str) -> dict:
    resp: dict = {
        "id": link.id,
        "self": f"{request.base_url}rest/api/2/issue/{issue_key}/remotelink/{link.id}",
        "application": {},
        "relationship": link.relationship_type or "links to",
        "object": {
            "url": link.url,
            "title": link.title,
            "icon": {
                "url16x16": link.icon_url or "",
                "title": link.icon_title or "",
            }
            if link.icon_url
            else {},
            "status": {"icon": {}},
        },
    }
    if link.global_id is not None:
        resp["globalId"] = link.global_id
    if link.summary is not None:
        resp["object"]["summary"] = link.summary
    return resp


async def _resolve_issue(db: AsyncSession, issue_key: str):
    issue = await issue_service.get_issue(db, issue_key)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue '{issue_key}' not found"]),
        )
    return issue


async def _resolve_link(db: AsyncSession, issue_id: int, link_id: int):
    result = await db.execute(select(RemoteLink).where(RemoteLink.id == link_id, RemoteLink.issue_id == issue_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Remote link with id '{link_id}' not found"]),
        )
    return link


def _extract_fields(body: dict) -> dict:
    obj = body.get("object", {})
    url = obj.get("url", "")
    title = obj.get("title", "")
    if not url:
        raise HTTPException(
            status_code=400,
            detail=_jira_error(["object.url is required"]),
        )
    if not title:
        raise HTTPException(
            status_code=400,
            detail=_jira_error(["object.title is required"]),
        )
    icon = obj.get("icon", {})
    return {
        "url": url,
        "title": title,
        "summary": obj.get("summary"),
        "icon_url": icon.get("url16x16") if icon else None,
        "icon_title": icon.get("title") if icon else None,
        "global_id": body.get("globalId"),
        "relationship_type": body.get("relationship"),
    }


@router.post("/issue/{issue_key}/remotelink", status_code=201)
async def create_remote_link(
    issue_key: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or upsert a remote link on an issue."""
    issue = await _resolve_issue(db, issue_key)
    body = await request.json()
    fields = _extract_fields(body)

    # Upsert: if globalId is provided and already exists for this issue, update in place
    existing = None
    if fields["global_id"]:
        result = await db.execute(
            select(RemoteLink).where(
                RemoteLink.issue_id == issue.id,
                RemoteLink.global_id == fields["global_id"],
            )
        )
        existing = result.scalar_one_or_none()

    if existing is not None:
        for attr, value in fields.items():
            setattr(existing, attr, value)
        await db.flush()
        return {
            "id": existing.id,
            "self": f"{request.base_url}rest/api/2/issue/{issue_key}/remotelink/{existing.id}",
        }

    link = RemoteLink(issue_id=issue.id, **fields)
    db.add(link)
    await db.flush()

    return {
        "id": link.id,
        "self": f"{request.base_url}rest/api/2/issue/{issue_key}/remotelink/{link.id}",
    }


@router.put("/issue/{issue_key}/remotelink/{link_id}")
async def update_remote_link(
    issue_key: str,
    link_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a remote link by ID (full replacement)."""
    issue = await _resolve_issue(db, issue_key)
    link = await _resolve_link(db, issue.id, link_id)
    body = await request.json()
    fields = _extract_fields(body)

    for attr, value in fields.items():
        setattr(link, attr, value)
    await db.flush()

    return {
        "id": link.id,
        "self": f"{request.base_url}rest/api/2/issue/{issue_key}/remotelink/{link.id}",
    }


@router.get("/issue/{issue_key}/remotelink")
async def list_remote_links(
    issue_key: str,
    request: Request,
    globalId: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List remote links, optionally filtered by globalId."""
    issue = await _resolve_issue(db, issue_key)

    stmt = select(RemoteLink).where(RemoteLink.issue_id == issue.id)
    if globalId is not None:
        stmt = stmt.where(RemoteLink.global_id == globalId)

    result = await db.execute(stmt)
    links = list(result.scalars().all())

    return [_link_response(link, request, issue_key) for link in links]


@router.get("/issue/{issue_key}/remotelink/{link_id}")
async def get_remote_link(
    issue_key: str,
    link_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single remote link by ID."""
    issue = await _resolve_issue(db, issue_key)
    link = await _resolve_link(db, issue.id, link_id)
    return _link_response(link, request, issue_key)


@router.delete("/issue/{issue_key}/remotelink/{link_id}", status_code=204)
async def delete_remote_link(
    issue_key: str,
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a remote link by ID."""
    issue = await _resolve_issue(db, issue_key)
    link = await _resolve_link(db, issue.id, link_id)
    await db.delete(link)
    await db.flush()
    return Response(status_code=204)


@router.delete("/issue/{issue_key}/remotelink", status_code=204)
async def delete_remote_link_by_global_id(
    issue_key: str,
    globalId: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a remote link by globalId."""
    issue = await _resolve_issue(db, issue_key)
    result = await db.execute(
        select(RemoteLink).where(
            RemoteLink.issue_id == issue.id,
            RemoteLink.global_id == globalId,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Remote link with globalId '{globalId}' not found"]),
        )
    await db.delete(link)
    await db.flush()
    return Response(status_code=204)
