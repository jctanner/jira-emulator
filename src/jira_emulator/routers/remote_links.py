"""Remote link endpoints: /rest/api/2/issue/{key}/remotelink."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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


@router.post("/issue/{issue_key}/remotelink", status_code=201)
async def create_remote_link(
    issue_key: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a remote link on an issue."""
    issue = await issue_service.get_issue(db, issue_key)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue '{issue_key}' not found"]),
        )

    body = await request.json()
    obj = body.get("object", {})
    url = obj.get("url", "")
    if not url:
        raise HTTPException(
            status_code=400,
            detail=_jira_error(["object.url is required"]),
        )

    icon = obj.get("icon", {})
    link = RemoteLink(
        issue_id=issue.id,
        url=url,
        title=obj.get("title"),
        icon_url=icon.get("url16x16") if icon else None,
        icon_title=icon.get("title") if icon else None,
    )
    db.add(link)
    await db.flush()

    return {"id": link.id, "self": f"{request.base_url}rest/api/2/issue/{issue_key}/remotelink/{link.id}"}


@router.get("/issue/{issue_key}/remotelink")
async def list_remote_links(
    issue_key: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all remote links for an issue."""
    issue = await issue_service.get_issue(db, issue_key)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue '{issue_key}' not found"]),
        )

    result = await db.execute(
        select(RemoteLink).where(RemoteLink.issue_id == issue.id)
    )
    links = list(result.scalars().all())

    return [
        {
            "id": link.id,
            "self": f"{request.base_url}rest/api/2/issue/{issue_key}/remotelink/{link.id}",
            "application": {},
            "object": {
                "url": link.url,
                "title": link.title or "",
                "icon": {
                    "url16x16": link.icon_url or "",
                    "title": link.icon_title or "",
                } if link.icon_url else {},
                "status": {"icon": {}},
            },
        }
        for link in links
    ]


@router.get("/issue/{issue_key}/remotelink/{link_id}")
async def get_remote_link(
    issue_key: str,
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single remote link by ID."""
    issue = await issue_service.get_issue(db, issue_key)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue '{issue_key}' not found"]),
        )

    result = await db.execute(
        select(RemoteLink).where(
            RemoteLink.id == link_id, RemoteLink.issue_id == issue.id
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Remote link with id '{link_id}' not found"]),
        )

    return {
        "id": link.id,
        "application": {},
        "object": {
            "url": link.url,
            "title": link.title or "",
            "icon": {
                "url16x16": link.icon_url or "",
                "title": link.icon_title or "",
            } if link.icon_url else {},
            "status": {"icon": {}},
        },
    }


@router.delete("/issue/{issue_key}/remotelink/{link_id}", status_code=204)
async def delete_remote_link(
    issue_key: str,
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a remote link by ID."""
    issue = await issue_service.get_issue(db, issue_key)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue '{issue_key}' not found"]),
        )

    result = await db.execute(
        select(RemoteLink).where(
            RemoteLink.id == link_id, RemoteLink.issue_id == issue.id
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Remote link with id '{link_id}' not found"]),
        )

    await db.delete(link)
    await db.flush()

    return Response(status_code=204)
