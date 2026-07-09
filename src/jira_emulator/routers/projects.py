"""Project and component endpoints: /rest/api/2/project and /rest/api/2/component."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.component import Component, IssueComponent
from jira_emulator.models.project import Project
from jira_emulator.models.user import User
from jira_emulator.services import project_service

router = APIRouter(prefix="/rest/api/2")


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


def _component_json(component: Component, base_url: str, issue_count: int | None = None) -> dict:
    project = component.project
    data = {
        "self": f"{base_url}/rest/api/2/component/{component.id}",
        "id": str(component.id),
        "name": component.name,
        "description": component.description or "",
        "assigneeType": "PROJECT_DEFAULT",
        "realAssigneeType": "PROJECT_DEFAULT",
        "isAssigneeTypeValid": True,
        "project": project.key,
        "projectId": project.id,
    }
    if issue_count is not None:
        data["issueCount"] = issue_count
    return data


def _component_sort_key(component: Component) -> tuple[str, str]:
    return (component.name.casefold(), component.name)


def _parse_component_id(component_id: str) -> int:
    try:
        return int(component_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"No component found with id '{component_id}'."]),
        ) from exc


async def _get_component(db: AsyncSession, component_id: str) -> Component:
    result = await db.execute(
        select(Component)
        .options(selectinload(Component.project))
        .where(Component.id == _parse_component_id(component_id))
    )
    component = result.scalar_one_or_none()
    if component is None:
        raise HTTPException(status_code=404, detail=_jira_error([f"No component found with id '{component_id}'."]))
    return component


async def _component_issue_count(db: AsyncSession, component_id: int) -> int:
    result = await db.execute(
        select(func.count(distinct(IssueComponent.issue_id))).where(IssueComponent.component_id == component_id)
    )
    return int(result.scalar_one())


async def _project_or_404(db: AsyncSession, project_id_or_key: str) -> Project:
    project = await project_service.get_project(db, project_id_or_key)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"No project could be found with key '{project_id_or_key}'."]),
        )
    return project


def _page(items: list[dict], start_at: int, max_results: int, self_url: str) -> dict:
    total = len(items)
    values = items[start_at : start_at + max_results]
    result = {
        "self": self_url,
        "startAt": start_at,
        "maxResults": max_results,
        "total": total,
        "isLast": start_at + max_results >= total,
        "values": values,
    }
    if start_at + max_results < total:
        separator = "&" if "?" in self_url else "?"
        result["nextPage"] = f"{self_url}{separator}startAt={start_at + max_results}&maxResults={max_results}"
    return result


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
        result.append(
            {
                "self": f"{base_url}/rest/api/2/project/{p.id}",
                "id": str(p.id),
                "key": p.key,
                "name": p.name,
                "projectTypeKey": p.project_type_key,
            }
        )

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

    project = await _project_or_404(db, projectIdOrKey)

    # Build issue types list from project associations
    issue_types = []
    for assoc in project.issue_type_associations:
        it = assoc.issue_type
        issue_types.append(
            {
                "self": f"{base_url}/rest/api/2/issuetype/{it.id}",
                "id": str(it.id),
                "description": it.description or "",
                "iconUrl": it.icon_url or "",
                "name": it.name,
                "subtask": it.subtask,
            }
        )

    # Build components list
    components = [_component_json(comp, base_url) for comp in sorted(project.components, key=_component_sort_key)]

    # Build versions list
    versions = []
    for ver in project.versions:
        versions.append(
            {
                "self": f"{base_url}/rest/api/2/version/{ver.id}",
                "id": str(ver.id),
                "name": ver.name,
                "description": ver.description or "",
                "released": ver.released,
                "releaseDate": str(ver.release_date) if ver.release_date else None,
            }
        )

    return {
        "self": f"{base_url}/rest/api/2/project/{project.id}",
        "id": str(project.id),
        "key": project.key,
        "name": project.name,
        "description": project.description or "",
        "lead": {
            "name": project.lead or "",
            "displayName": project.lead or "",
        }
        if project.lead
        else None,
        "projectTypeKey": project.project_type_key,
        "issueTypes": issue_types,
        "components": components,
        "versions": versions,
    }


@router.get("/project/{projectIdOrKey}/components")
async def list_project_components(
    projectIdOrKey: str,
    componentSource: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all components in a project."""
    settings = get_settings()
    project = await _project_or_404(db, projectIdOrKey)
    return [_component_json(comp, settings.BASE_URL) for comp in sorted(project.components, key=_component_sort_key)]


@router.get("/project/{projectIdOrKey}/component")
async def list_project_components_paginated(
    projectIdOrKey: str,
    request: Request,
    startAt: int = Query(0, ge=0),
    maxResults: int = Query(50, ge=1),
    orderBy: str | None = None,
    query: str | None = None,
    componentSource: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of project components."""
    settings = get_settings()
    project = await _project_or_404(db, projectIdOrKey)

    components = list(project.components)
    if query:
        query_folded = query.casefold()
        components = [component for component in components if query_folded in component.name.casefold()]
    components.sort(key=_component_sort_key, reverse=orderBy == "-name")

    values = [
        _component_json(component, settings.BASE_URL, issue_count=await _component_issue_count(db, component.id))
        for component in components
    ]
    return _page(values, startAt, maxResults, str(request.url))


@router.get("/component")
async def list_components(
    request: Request,
    startAt: int = Query(0, ge=0),
    maxResults: int = Query(50, ge=1),
    orderBy: str | None = None,
    query: str | None = None,
    projectIdsOrKeys: list[str] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of components across projects."""
    settings = get_settings()
    stmt = select(Component).options(selectinload(Component.project))

    project_filters: list[str] = []
    for value in projectIdsOrKeys or []:
        project_filters.extend(part.strip() for part in value.split(",") if part.strip())
    if project_filters:
        projects = []
        for project_id_or_key in project_filters:
            project = await _project_or_404(db, project_id_or_key)
            projects.append(project.id)
        stmt = stmt.where(Component.project_id.in_(projects))

    components = list((await db.execute(stmt)).scalars().all())
    if query:
        query_folded = query.casefold()
        components = [component for component in components if query_folded in component.name.casefold()]
    components.sort(key=_component_sort_key, reverse=orderBy == "-name")

    values = [_component_json(component, settings.BASE_URL) for component in components]
    return _page(values, startAt, maxResults, str(request.url))


@router.post("/component", status_code=201)
async def create_component(
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a project component."""
    name = body.get("name")
    project_key = body.get("project")
    if not isinstance(name, str) or not name:
        raise HTTPException(status_code=400, detail=_jira_error(["Component name is required."]))
    if not isinstance(project_key, str) or not project_key:
        raise HTTPException(status_code=400, detail=_jira_error(["Component project is required."]))

    project = await _project_or_404(db, project_key)
    existing = (
        await db.execute(select(Component).where(Component.project_id == project.id, Component.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail=_jira_error([f"A component with name '{name}' already exists."]))

    component = Component(
        project_id=project.id,
        name=name,
        description=body.get("description") if isinstance(body.get("description"), str) else None,
        lead=body.get("leadUserName") if isinstance(body.get("leadUserName"), str) else None,
    )
    db.add(component)
    await db.flush()
    await db.refresh(component, attribute_names=["project"])
    await db.commit()

    return _component_json(component, get_settings().BASE_URL)


@router.get("/component/{component_id}/relatedIssueCounts")
async def get_component_related_issue_counts(
    component_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the count of issues assigned to a component."""
    component = await _get_component(db, component_id)
    return {
        "self": f"{get_settings().BASE_URL}/rest/api/2/component/{component.id}",
        "issueCount": await _component_issue_count(db, component.id),
    }


@router.get("/component/{component_id}")
async def get_component(
    component_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return one component."""
    return _component_json(await _get_component(db, component_id), get_settings().BASE_URL)


@router.put("/component/{component_id}")
async def update_component(
    component_id: str,
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update one component."""
    component = await _get_component(db, component_id)
    if "project" in body and body["project"] not in (component.project.key, str(component.project_id)):
        raise HTTPException(
            status_code=400,
            detail=_jira_error(["Moving components between projects is not supported."]),
        )

    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=400, detail=_jira_error(["Component name must not be empty."]))
        duplicate = (
            await db.execute(
                select(Component).where(
                    Component.project_id == component.project_id,
                    Component.name == name,
                    Component.id != component.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(
                status_code=400,
                detail=_jira_error([f"A component with name '{name}' already exists."]),
            )
        component.name = name

    if "description" in body:
        component.description = body["description"] if isinstance(body["description"], str) else None
    if "leadUserName" in body:
        component.lead = (
            body["leadUserName"] if isinstance(body["leadUserName"], str) and body["leadUserName"] else None
        )

    await db.commit()
    await db.refresh(component, attribute_names=["project"])
    return _component_json(component, get_settings().BASE_URL)


@router.delete("/component/{component_id}", status_code=204)
async def delete_component(
    component_id: str,
    moveIssuesTo: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one component, optionally moving issue associations."""
    component = await _get_component(db, component_id)
    target = await _get_component(db, moveIssuesTo) if moveIssuesTo else None
    if target is not None and target.project_id != component.project_id:
        raise HTTPException(
            status_code=400,
            detail=_jira_error(["moveIssuesTo must reference a component in the same project."]),
        )

    associations = (
        await db.execute(select(IssueComponent).where(IssueComponent.component_id == component.id))
    ).scalars().all()
    if target is not None:
        for association in associations:
            existing = (
                await db.execute(
                    select(IssueComponent).where(
                        IssueComponent.issue_id == association.issue_id,
                        IssueComponent.component_id == target.id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(IssueComponent(issue_id=association.issue_id, component_id=target.id))

    for association in associations:
        await db.delete(association)
    await db.delete(component)
    await db.commit()
    return Response(status_code=204)
