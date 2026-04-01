"""Issue link endpoints: /rest/api/2/issueLink and /rest/api/2/issueLinkType."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.link import IssueLinkType, IssueLink
from jira_emulator.models.user import User
from jira_emulator.services import issue_service

router = APIRouter(prefix="/rest/api/2")


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


@router.post("/issueLink", status_code=201)
async def create_issue_link(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an issue link between two issues.

    Expects a JSON body like::

        {
            "type": {"name": "Blocks"},
            "inwardIssue": {"key": "PROJ-1"},
            "outwardIssue": {"key": "PROJ-2"}
        }
    """
    body = await request.json()

    # -- look up link type by name --
    type_data = body.get("type", {})
    type_name = type_data.get("name")
    if not type_name:
        raise HTTPException(status_code=400, detail=_jira_error(["type.name is required"]))

    result = await db.execute(
        select(IssueLinkType).where(IssueLinkType.name == type_name)
    )
    link_type = result.scalar_one_or_none()
    if link_type is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue link type '{type_name}' not found"]),
        )

    # -- look up inward issue --
    inward_data = body.get("inwardIssue", {})
    inward_key = inward_data.get("key")
    if not inward_key:
        raise HTTPException(status_code=400, detail=_jira_error(["inwardIssue.key is required"]))

    inward_issue = await issue_service.get_issue(db, inward_key)
    if inward_issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue '{inward_key}' not found"]),
        )

    # -- look up outward issue --
    outward_data = body.get("outwardIssue", {})
    outward_key = outward_data.get("key")
    if not outward_key:
        raise HTTPException(status_code=400, detail=_jira_error(["outwardIssue.key is required"]))

    outward_issue = await issue_service.get_issue(db, outward_key)
    if outward_issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue '{outward_key}' not found"]),
        )

    # -- create the link --
    link = IssueLink(
        link_type_id=link_type.id,
        inward_issue_id=inward_issue.id,
        outward_issue_id=outward_issue.id,
    )
    db.add(link)
    await db.flush()

    return Response(status_code=201)


@router.delete("/issueLink/{link_id}", status_code=204)
async def delete_issue_link(
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an issue link by ID."""
    result = await db.execute(
        select(IssueLink).where(IssueLink.id == link_id)
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue link with id '{link_id}' not found"]),
        )

    await db.delete(link)
    await db.flush()

    return Response(status_code=204)


@router.get("/issueLinkType")
async def list_issue_link_types(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all issue link types."""
    settings = get_settings()
    base_url = settings.BASE_URL

    result = await db.execute(select(IssueLinkType).order_by(IssueLinkType.id))
    link_types = list(result.scalars().all())

    return {
        "issueLinkTypes": [
            {
                "id": str(lt.id),
                "name": lt.name,
                "inward": lt.inward_description or "",
                "outward": lt.outward_description or "",
                "self": f"{base_url}/rest/api/2/issueLinkType/{lt.id}",
            }
            for lt in link_types
        ]
    }
