"""Project endpoints: /rest/api/2/project."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.user import User
from jira_emulator.services import project_service

router = APIRouter(prefix="/rest/api/2")


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


@router.get("/project")
async def list_projects(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    settings = get_settings()
    base_url = settings.BASE_URL

    projects = await project_service.list_projects(db)

    result = []
    for p in projects:
        result.append({
            "self": f"{base_url}/rest/api/2/project/{p.id}",
            "id": str(p.id),
            "key": p.key,
            "name": p.name,
            "projectTypeKey": p.project_type_key,
        })

    return result


@router.get("/project/{projectIdOrKey}")
async def get_project(
    projectIdOrKey: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get project details including components, issue types, and versions."""
    settings = get_settings()
    base_url = settings.BASE_URL

    project = await project_service.get_project(db, projectIdOrKey)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"No project could be found with key '{projectIdOrKey}'."]),
        )

    # Build issue types list from project associations
    issue_types = []
    for assoc in project.issue_type_associations:
        it = assoc.issue_type
        issue_types.append({
            "self": f"{base_url}/rest/api/2/issuetype/{it.id}",
            "id": str(it.id),
            "description": it.description or "",
            "iconUrl": it.icon_url or "",
            "name": it.name,
            "subtask": it.subtask,
        })

    # Build components list
    components = []
    for comp in project.components:
        components.append({
            "self": f"{base_url}/rest/api/2/component/{comp.id}",
            "id": str(comp.id),
            "name": comp.name,
            "description": comp.description or "",
        })

    # Build versions list
    versions = []
    for ver in project.versions:
        versions.append({
            "self": f"{base_url}/rest/api/2/version/{ver.id}",
            "id": str(ver.id),
            "name": ver.name,
            "description": ver.description or "",
            "released": ver.released,
            "releaseDate": str(ver.release_date) if ver.release_date else None,
        })

    return {
        "self": f"{base_url}/rest/api/2/project/{project.id}",
        "id": str(project.id),
        "key": project.key,
        "name": project.name,
        "description": project.description or "",
        "lead": {
            "name": project.lead or "",
            "displayName": project.lead or "",
        } if project.lead else None,
        "projectTypeKey": project.project_type_key,
        "issueTypes": issue_types,
        "components": components,
        "versions": versions,
    }
