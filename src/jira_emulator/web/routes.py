"""Web UI routes for the Jira Emulator."""

import json
import logging
import math
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator import __version__
from jira_emulator.database import get_db
from jira_emulator.config import get_settings
from jira_emulator.models.attachment import Attachment
from jira_emulator.models.comment import Comment
from jira_emulator.models.issue import Issue
from jira_emulator.models.project import Project
from jira_emulator.models.user import User
from jira_emulator.models.status import Status
from jira_emulator.models.issue_type import IssueType
from jira_emulator.models.priority import Priority
from jira_emulator.services import issue_service, search_service, history_service
from jira_emulator.services.user_service import get_or_create_user

logger = logging.getLogger(__name__)

# Template directory is relative to this file
import os

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET / — Home page
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    """Dashboard showing project list and summary statistics."""

    # Total counts
    total_issues = (await db.execute(select(func.count(Issue.id)))).scalar_one()
    total_projects = (await db.execute(select(func.count(Project.id)))).scalar_one()
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()

    # Projects with per-project issue counts
    stmt = (
        select(Project.key, Project.name, func.count(Issue.id).label("issue_count"))
        .outerjoin(Issue, Issue.project_id == Project.id)
        .group_by(Project.id)
        .order_by(Project.key)
    )
    rows = (await db.execute(stmt)).all()
    projects = [
        {"key": r.key, "name": r.name, "issue_count": r.issue_count} for r in rows
    ]

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "projects": projects,
            "total_issues": total_issues,
            "total_projects": total_projects,
            "total_users": total_users,
            "version": __version__,
        },
    )


# ---------------------------------------------------------------------------
# GET /project/{key} — Project detail
# ---------------------------------------------------------------------------
@router.get("/project/{key}", response_class=HTMLResponse)
async def project_detail(request: Request, key: str, db: AsyncSession = Depends(get_db)):
    """Show a single project with status and type breakdowns."""

    result = await db.execute(select(Project).where(Project.key == key))
    project = result.scalar_one_or_none()
    if project is None:
        return HTMLResponse("<h1>Project not found</h1>", status_code=404)

    # Issue counts by status
    status_stmt = (
        select(Status.name, func.count(Issue.id).label("count"))
        .join(Issue, Issue.status_id == Status.id)
        .where(Issue.project_id == project.id)
        .group_by(Status.name)
        .order_by(Status.name)
    )
    status_rows = (await db.execute(status_stmt)).all()
    status_counts = [{"name": r.name, "count": r.count} for r in status_rows]

    # Issue counts by type
    type_stmt = (
        select(IssueType.name, func.count(Issue.id).label("count"))
        .join(Issue, Issue.issue_type_id == IssueType.id)
        .where(Issue.project_id == project.id)
        .group_by(IssueType.name)
        .order_by(IssueType.name)
    )
    type_rows = (await db.execute(type_stmt)).all()
    type_counts = [{"name": r.name, "count": r.count} for r in type_rows]

    total_issues = sum(sc["count"] for sc in status_counts)

    return templates.TemplateResponse(
        request=request,
        name="project.html",
        context={
            "project": project,
            "status_counts": status_counts,
            "type_counts": type_counts,
            "total_issues": total_issues,
            "version": __version__,
        },
    )


# ---------------------------------------------------------------------------
# GET /issues — Issue list with filtering
# ---------------------------------------------------------------------------
@router.get("/issues", response_class=HTMLResponse)
async def issue_list(
    request: Request,
    jql: str | None = None,
    project: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    sort: str = "created",
    order: str = "DESC",
    db: AsyncSession = Depends(get_db),
):
    """Paginated, filterable issue list."""

    page_size = 25
    if page < 1:
        page = 1

    jql_error = None

    if jql:
        # Use raw JQL directly
        search_jql = jql
    else:
        # Build JQL from quick-filter parameters
        jql_parts: list[str] = []
        if project:
            jql_parts.append(f'project = "{project}"')
        if status:
            jql_parts.append(f'status = "{status}"')
        if q:
            jql_parts.append(f'summary ~ "{q}"')

        search_jql = " AND ".join(jql_parts) if jql_parts else "ORDER BY created DESC"

        if jql_parts:
            search_jql += f" ORDER BY {sort} {order}"

    start_at = (page - 1) * page_size

    try:
        search_result = await search_service.search_issues(
            db=db,
            jql=search_jql,
            start_at=start_at,
            max_results=page_size,
            current_user=None,
            base_url=str(request.base_url).rstrip("/"),
        )
        issues = search_result["issues"]
        total = search_result["total"]
    except (ValueError, Exception) as exc:
        logger.warning("JQL search failed: %s", exc)
        jql_error = str(exc)
        issues = []
        total = 0

    total_pages = max(1, math.ceil(total / page_size))

    # Dropdown data (only needed when not using raw JQL)
    all_projects = (
        (await db.execute(select(Project).order_by(Project.key))).scalars().all()
    )
    all_statuses = (
        (await db.execute(select(Status).order_by(Status.name))).scalars().all()
    )

    filters = {
        "jql": jql or "",
        "project": project or "",
        "status": status or "",
        "q": q or "",
        "sort": sort,
        "order": order,
    }

    return templates.TemplateResponse(
        request=request,
        name="issues.html",
        context={
            "issues": issues,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "projects": all_projects,
            "statuses": all_statuses,
            "filters": filters,
            "jql_error": jql_error,
            "version": __version__,
        },
    )


# ---------------------------------------------------------------------------
# GET /issue/{key} — Issue detail
# ---------------------------------------------------------------------------
@router.get("/issue/{key}", response_class=HTMLResponse)
async def issue_detail(request: Request, key: str, db: AsyncSession = Depends(get_db)):
    """Full issue detail view."""

    issue = await issue_service.get_issue(db, key)
    if issue is None:
        return HTMLResponse("<h1>Issue not found</h1>", status_code=404)

    base_url = str(request.base_url).rstrip("/")
    formatted = await issue_service.format_issue_response(issue, base_url, db)

    # Load metadata for the edit modal
    all_projects = (
        (await db.execute(select(Project).order_by(Project.key))).scalars().all()
    )
    all_types = (
        (await db.execute(select(IssueType).order_by(IssueType.name))).scalars().all()
    )
    all_priorities = (
        (await db.execute(select(Priority).order_by(Priority.id))).scalars().all()
    )
    all_statuses = (
        (await db.execute(select(Status).order_by(Status.name))).scalars().all()
    )
    all_users = (
        (await db.execute(select(User).where(User.active.is_(True)).order_by(User.display_name))).scalars().all()
    )

    return templates.TemplateResponse(
        request=request,
        name="issue_detail.html",
        context={
            "issue": formatted,
            "projects": all_projects,
            "issue_types": all_types,
            "priorities": all_priorities,
            "statuses": all_statuses,
            "users": all_users,
            "version": __version__,
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/import — Import form
# ---------------------------------------------------------------------------
@router.get("/admin/import", response_class=HTMLResponse)
async def admin_import_form(request: Request):
    """Render the JSON import upload form."""
    return templates.TemplateResponse(
        request=request,
        name="admin_import.html",
        context={
            "version": __version__,
        },
    )


# ---------------------------------------------------------------------------
# POST /admin/import — Handle import upload
# ---------------------------------------------------------------------------
@router.post("/admin/reset")
async def admin_reset(request: Request):
    """Reset the database to seed data only and redirect to home."""
    from jira_emulator.database import Base, get_engine, get_session_factory
    from jira_emulator.services.seed_service import load_seed_data

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        await load_seed_data(session)

    return RedirectResponse(url="/", status_code=303)


@router.post("/admin/import", response_class=HTMLResponse)
async def admin_import_upload(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Accept a JSON file upload and import issues."""
    from jira_emulator.services.import_service import import_issues

    try:
        content = await file.read()
        data = json.loads(content)

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            raise ValueError(
                f"Expected a JSON array or object, got {type(data).__name__}"
            )

        result = await import_issues(db, data)

        return templates.TemplateResponse(
            request=request,
            name="admin_import.html",
            context={
                "result": {
                    "imported": result.imported,
                    "updated": result.updated,
                    "errors": result.errors,
                    "projects_created": result.projects_created,
                    "users_created": result.users_created,
                },
                "version": __version__,
            },
        )
    except json.JSONDecodeError as exc:
        return templates.TemplateResponse(
            request=request,
            name="admin_import.html",
            context={
                "result": {
                    "imported": 0,
                    "updated": 0,
                    "errors": [f"Invalid JSON: {exc}"],
                    "projects_created": [],
                    "users_created": [],
                },
                "version": __version__,
            },
        )
    except Exception as exc:
        logger.exception("Import failed")
        return templates.TemplateResponse(
            request=request,
            name="admin_import.html",
            context={
                "result": {
                    "imported": 0,
                    "updated": 0,
                    "errors": [str(exc)],
                    "projects_created": [],
                    "users_created": [],
                },
                "version": __version__,
            },
        )


# ---------------------------------------------------------------------------
# GET /api/web/create-metadata — JSON for the create-issue modal
# ---------------------------------------------------------------------------
@router.get("/api/web/create-metadata")
async def create_metadata(db: AsyncSession = Depends(get_db)):
    """Return projects, issue types, priorities, and users for the create form."""
    projects = (
        (await db.execute(select(Project).order_by(Project.key))).scalars().all()
    )
    issue_types = (
        (await db.execute(select(IssueType).order_by(IssueType.name))).scalars().all()
    )
    priorities = (
        (await db.execute(select(Priority).order_by(Priority.id))).scalars().all()
    )
    users = (
        (await db.execute(select(User).where(User.active.is_(True)).order_by(User.display_name))).scalars().all()
    )
    return JSONResponse({
        "projects": [{"key": p.key, "name": p.name} for p in projects],
        "issueTypes": [{"name": t.name} for t in issue_types],
        "priorities": [{"name": p.name} for p in priorities],
        "users": [{"name": u.username, "displayName": u.display_name} for u in users],
    })


# ---------------------------------------------------------------------------
# POST /issue/create — Create issue from web form
# ---------------------------------------------------------------------------
@router.post("/issue/create")
async def create_issue_web(
    request: Request,
    db: AsyncSession = Depends(get_db),
    project: str = Form(...),
    issuetype: str = Form(...),
    summary: str = Form(...),
    description: str = Form(""),
    priority: str = Form(""),
    assignee: str = Form(""),
    labels: str = Form(""),
):
    """Create an issue from the web modal form and redirect to it."""
    # Build fields dict matching what issue_service.create_issue expects
    fields: dict = {
        "project": {"key": project},
        "issuetype": {"name": issuetype},
        "summary": summary,
    }
    if description:
        fields["description"] = description
    if priority:
        fields["priority"] = {"name": priority}
    if assignee:
        fields["assignee"] = {"name": assignee}
    if labels:
        fields["labels"] = [l.strip() for l in labels.split(",") if l.strip()]

    # Use the admin user as the reporter/current_user
    admin = await get_or_create_user(db, "admin", "admin")

    try:
        issue = await issue_service.create_issue(db, fields, admin)
        await db.commit()
        return RedirectResponse(url=f"/issue/{issue.key}", status_code=303)
    except ValueError as exc:
        logger.warning("Create issue failed: %s", exc)
        return HTMLResponse(
            f"<h1>Error creating issue</h1><p>{exc}</p><p><a href='/issues'>Back to issues</a></p>",
            status_code=400,
        )


# ---------------------------------------------------------------------------
# POST /issue/{key}/edit — Update issue from web form
# ---------------------------------------------------------------------------
@router.post("/issue/{key}/edit")
async def edit_issue_web(
    key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    summary: str = Form(...),
    description: str = Form(""),
    priority: str = Form(""),
    assignee: str = Form(""),
    status: str = Form(""),
    labels: str = Form(""),
):
    """Update an issue from the edit modal and redirect back to it."""
    fields: dict = {
        "summary": summary,
        "description": description,
        "labels": [l.strip() for l in labels.split(",") if l.strip()] if labels else [],
    }
    if priority:
        fields["priority"] = {"name": priority}
    else:
        fields["priority"] = None
    if assignee:
        fields["assignee"] = {"name": assignee}
    else:
        fields["assignee"] = None

    try:
        # Use the admin user as the author for web edits
        admin = await get_or_create_user(db, "admin", "admin")

        await issue_service.update_issue(db, key, fields=fields, author_id=admin.id)

        # Handle status change directly (bypass workflow for web UI flexibility)
        if status:
            issue = await issue_service.get_issue(db, key)
            if issue and issue.status and issue.status.name != status:
                old_status_name = issue.status.name
                old_status_id = str(issue.status_id)
                result = await db.execute(select(Status).where(Status.name == status))
                new_status = result.scalar_one_or_none()
                if new_status:
                    issue.status_id = new_status.id
                    issue.status = new_status
                    await history_service.record_change(
                        db, issue.id, admin.id, "status",
                        old_status_name, old_status_id,
                        new_status.name, str(new_status.id),
                    )

        await db.commit()
        return RedirectResponse(url=f"/issue/{key}", status_code=303)
    except ValueError as exc:
        logger.warning("Edit issue failed: %s", exc)
        return HTMLResponse(
            f"<h1>Error updating issue</h1><p>{exc}</p><p><a href='/issue/{key}'>Back to issue</a></p>",
            status_code=400,
        )


# ---------------------------------------------------------------------------
# POST /issue/{key}/comment — Add comment from web UI
# ---------------------------------------------------------------------------
@router.post("/issue/{key}/comment")
async def add_comment_web(
    key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    body: str = Form(...),
):
    """Add a comment to an issue from the web UI and redirect back."""
    from datetime import datetime

    issue = await issue_service.get_issue(db, key)
    if issue is None:
        return HTMLResponse("<h1>Issue not found</h1>", status_code=404)

    admin = await get_or_create_user(db, "admin", "admin")

    now = datetime.utcnow()
    comment = Comment(
        issue_id=issue.id,
        author_id=admin.id,
        body=body,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)
    await db.flush()

    await history_service.record_change(
        db, issue.id, admin.id, "Comment",
        None, None, body, str(comment.id),
    )

    await db.commit()

    return RedirectResponse(url=f"/issue/{key}", status_code=303)


# ---------------------------------------------------------------------------
# POST /issue/{key}/attachment — Upload attachment from web UI
# ---------------------------------------------------------------------------
@router.post("/issue/{key}/attachment")
async def upload_attachment_web(
    key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Upload file attachments from the web UI and redirect back to the issue."""
    import mimetypes as mt

    issue = await issue_service.get_issue(db, key)
    if issue is None:
        return HTMLResponse("<h1>Issue not found</h1>", status_code=404)

    admin = await get_or_create_user(db, "admin", "admin")

    settings = get_settings()
    attachment_dir = settings.ATTACHMENT_DIR
    os.makedirs(attachment_dir, exist_ok=True)

    form = await request.form()
    files = form.getlist("file")

    now = datetime.utcnow()
    for upload in files:
        content = await upload.read()
        filename = upload.filename or "unnamed"
        mime = upload.content_type or mt.guess_type(filename)[0] or "application/octet-stream"
        size = len(content)

        attachment = Attachment(
            issue_id=issue.id,
            author_id=admin.id,
            filename=filename,
            size=size,
            mime_type=mime,
            file_path="",
            created_at=now,
        )
        db.add(attachment)
        await db.flush()

        disk_filename = f"{attachment.id}_{filename}"
        disk_path = os.path.join(attachment_dir, disk_filename)
        attachment.file_path = disk_filename

        with open(disk_path, "wb") as f:
            f.write(content)

        await history_service.record_change(
            db, issue.id, admin.id, "Attachment",
            None, None, filename, str(attachment.id),
        )

    await db.commit()
    return RedirectResponse(url=f"/issue/{key}", status_code=303)


# ---------------------------------------------------------------------------
# POST /issue/{key}/attachment/{attachment_id}/delete — Delete attachment from web UI
# ---------------------------------------------------------------------------
@router.post("/issue/{key}/attachment/{attachment_id}/delete")
async def delete_attachment_web(
    key: str,
    attachment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete an attachment from the web UI and redirect back to the issue."""
    from sqlalchemy import select as sa_select

    issue = await issue_service.get_issue(db, key)
    if issue is None:
        return HTMLResponse("<h1>Issue not found</h1>", status_code=404)

    result = await db.execute(
        sa_select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.issue_id == issue.id,
        )
    )
    att = result.scalar_one_or_none()
    if att is None:
        return HTMLResponse("<h1>Attachment not found</h1>", status_code=404)

    admin = await get_or_create_user(db, "admin", "admin")

    await history_service.record_change(
        db, issue.id, admin.id, "Attachment",
        att.filename, str(att.id), None, None,
    )

    settings = get_settings()
    disk_path = os.path.join(settings.ATTACHMENT_DIR, att.file_path)
    if os.path.exists(disk_path):
        os.remove(disk_path)

    await db.delete(att)
    await db.commit()

    return RedirectResponse(url=f"/issue/{key}", status_code=303)
