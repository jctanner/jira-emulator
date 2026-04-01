"""Metadata listing endpoints: priorities, statuses, resolutions, issue types."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.issue_type import IssueType
from jira_emulator.models.priority import Priority
from jira_emulator.models.resolution import Resolution
from jira_emulator.models.status import Status
from jira_emulator.models.user import User

router = APIRouter(prefix="/rest/api/2")


def _status_category_for(category: str) -> dict:
    """Map a status category string to a Jira StatusCategory dict."""
    categories = {
        "new": {"self": "", "id": "2", "key": "new", "colorName": "blue-gray", "name": "To Do"},
        "indeterminate": {"self": "", "id": "4", "key": "indeterminate", "colorName": "yellow", "name": "In Progress"},
        "done": {"self": "", "id": "3", "key": "done", "colorName": "green", "name": "Done"},
    }
    return categories.get(category, categories["indeterminate"])


@router.get("/priority")
async def list_priorities(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all priorities."""
    settings = get_settings()
    base_url = settings.BASE_URL

    result = await db.execute(select(Priority).order_by(Priority.sort_order))
    priorities = list(result.scalars().all())

    return [
        {
            "self": f"{base_url}/rest/api/2/priority/{p.id}",
            "id": str(p.id),
            "name": p.name,
            "iconUrl": p.icon_url or "",
            "statusColor": "",
            "description": "",
        }
        for p in priorities
    ]


@router.get("/status")
async def list_statuses(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all statuses."""
    settings = get_settings()
    base_url = settings.BASE_URL

    result = await db.execute(select(Status).order_by(Status.id))
    statuses = list(result.scalars().all())

    return [
        {
            "self": f"{base_url}/rest/api/2/status/{s.id}",
            "id": str(s.id),
            "name": s.name,
            "description": s.description or "",
            "iconUrl": "",
            "statusCategory": _status_category_for(s.category),
        }
        for s in statuses
    ]


@router.get("/resolution")
async def list_resolutions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all resolutions."""
    settings = get_settings()
    base_url = settings.BASE_URL

    result = await db.execute(select(Resolution).order_by(Resolution.id))
    resolutions = list(result.scalars().all())

    return [
        {
            "self": f"{base_url}/rest/api/2/resolution/{r.id}",
            "id": str(r.id),
            "name": r.name,
            "description": r.description or "",
        }
        for r in resolutions
    ]


@router.get("/issuetype")
async def list_issue_types(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all issue types."""
    settings = get_settings()
    base_url = settings.BASE_URL

    result = await db.execute(select(IssueType).order_by(IssueType.id))
    issue_types = list(result.scalars().all())

    return [
        {
            "self": f"{base_url}/rest/api/2/issuetype/{it.id}",
            "id": str(it.id),
            "name": it.name,
            "description": it.description or "",
            "iconUrl": it.icon_url or "",
            "subtask": it.subtask,
        }
        for it in issue_types
    ]
