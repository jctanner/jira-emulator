"""Issue CRUD endpoints and comments: /rest/api/2/issue/..."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.comment import Comment
from jira_emulator.models.user import User
from jira_emulator.models.watcher import Watcher
from jira_emulator.schemas.comment import CreateCommentRequest
from jira_emulator.schemas.issue import (
    CreateIssueRequest,
    TransitionRequest,
    UpdateIssueRequest,
)
from jira_emulator.adf import serialize_adf
from jira_emulator.services import issue_service, history_service
from jira_emulator.services.issue_service import _format_rich_field
from jira_emulator.services.user_service import get_or_create_user

router = APIRouter(prefix="/rest/api/2")


def _get_api_version(request: Request) -> int:
    return getattr(request.state, "api_version", 2)


def _format_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}+0000"


def _format_user(user: User | None, base_url: str) -> dict | None:
    if user is None:
        return None
    return {
        "self": f"{base_url}/rest/api/2/user?username={user.username}",
        "name": user.username,
        "key": user.username,
        "emailAddress": user.email or "",
        "displayName": user.display_name,
        "active": user.active,
    }


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


# ---------------------------------------------------------------------------
# Issue CRUD
# ---------------------------------------------------------------------------


@router.post("/issue", status_code=201)
async def create_issue(
    body: CreateIssueRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new issue."""
    settings = get_settings()
    base_url = settings.BASE_URL

    try:
        issue = await issue_service.create_issue(db, body.fields, current_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_jira_error([str(exc)]),
        )

    return {
        "id": str(issue.id),
        "key": issue.key,
        "self": f"{base_url}/rest/api/2/issue/{issue.id}",
    }


@router.get("/issue/{issueIdOrKey}")
async def get_issue(
    issueIdOrKey: str,
    request: Request,
    fields: str | None = Query(default=None),
    expand: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single issue by key or id."""
    settings = get_settings()
    base_url = settings.BASE_URL

    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )

    fields_filter = None
    if fields:
        fields_filter = [f.strip() for f in fields.split(",")]

    return await issue_service.format_issue_response(
        issue, base_url, db, fields_filter=fields_filter,
        api_version=_get_api_version(request),
    )


@router.put("/issue/{issueIdOrKey}")
async def update_issue(
    issueIdOrKey: str,
    body: UpdateIssueRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing issue."""
    try:
        await issue_service.update_issue(
            db,
            issueIdOrKey,
            fields=body.fields,
            update_ops=body.update,
            author_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([str(exc)]),
        )

    return Response(status_code=204)


@router.delete("/issue/{issueIdOrKey}")
async def delete_issue(
    issueIdOrKey: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an issue."""
    deleted = await issue_service.delete_issue(db, issueIdOrKey)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


@router.get("/issue/{issueIdOrKey}/comment")
async def list_comments(
    issueIdOrKey: str,
    request: Request,
    startAt: int = Query(default=0),
    maxResults: int = Query(default=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List comments for an issue."""
    settings = get_settings()
    base_url = settings.BASE_URL

    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )

    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.issue_id == issue.id)
        .order_by(Comment.created_at)
        .offset(startAt)
        .limit(maxResults)
    )
    comments = list(result.scalars().all())

    # Get total count
    from sqlalchemy import func

    count_result = await db.execute(
        select(func.count()).select_from(Comment).where(Comment.issue_id == issue.id)
    )
    total = count_result.scalar() or 0

    api_version = _get_api_version(request)
    comment_dicts = []
    for c in comments:
        comment_dicts.append({
            "self": f"{base_url}/rest/api/2/issue/{issue.id}/comment/{c.id}",
            "id": str(c.id),
            "author": _format_user(c.author, base_url),
            "updateAuthor": _format_user(c.author, base_url),
            "body": _format_rich_field(c.body, api_version),
            "created": _format_datetime(c.created_at),
            "updated": _format_datetime(c.updated_at),
            "visibility": (
                {"type": c.visibility_type, "value": c.visibility_value}
                if c.visibility_type
                else None
            ),
        })

    return {
        "startAt": startAt,
        "maxResults": maxResults,
        "total": total,
        "comments": comment_dicts,
    }


@router.post("/issue/{issueIdOrKey}/comment", status_code=201)
async def add_comment(
    issueIdOrKey: str,
    body: CreateCommentRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to an issue."""
    settings = get_settings()
    base_url = settings.BASE_URL

    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )

    # Ensure author user exists
    author = await get_or_create_user(
        db,
        display_name=current_user.display_name,
        username=current_user.username,
    )

    stored_body = serialize_adf(body.body) or ""

    now = datetime.utcnow()
    comment = Comment(
        issue_id=issue.id,
        author_id=author.id,
        body=stored_body,
        visibility_type=body.visibility.get("type") if body.visibility else None,
        visibility_value=body.visibility.get("value") if body.visibility else None,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)
    await db.flush()

    await history_service.record_change(
        db, issue.id, author.id, "Comment",
        None, None, comment.body, str(comment.id),
    )

    api_version = _get_api_version(request)
    return {
        "self": f"{base_url}/rest/api/2/issue/{issue.id}/comment/{comment.id}",
        "id": str(comment.id),
        "author": _format_user(author, base_url),
        "updateAuthor": _format_user(author, base_url),
        "body": _format_rich_field(comment.body, api_version),
        "created": _format_datetime(comment.created_at),
        "updated": _format_datetime(comment.updated_at),
    }


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


@router.get("/issue/{issueIdOrKey}/transitions")
async def get_transitions(
    issueIdOrKey: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get available transitions for an issue."""
    settings = get_settings()
    base_url = settings.BASE_URL

    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )

    from jira_emulator.services import workflow_service
    from jira_emulator.services.issue_service import _status_category_for

    transitions = await workflow_service.get_available_transitions(db, issue)

    trans_list = []
    for t in transitions:
        to_status = t.to_status
        cat = _status_category_for(to_status.category)
        trans_list.append({
            "id": str(t.id),
            "name": t.name,
            "to": {
                "self": f"{base_url}/rest/api/2/status/{to_status.id}",
                "description": "",
                "iconUrl": "",
                "name": to_status.name,
                "id": str(to_status.id),
                "statusCategory": cat,
            },
        })

    return {"expand": "transitions", "transitions": trans_list}


@router.post("/issue/{issueIdOrKey}/transitions")
async def perform_transition(
    issueIdOrKey: str,
    body: TransitionRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Perform a transition on an issue."""
    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )

    from jira_emulator.services import workflow_service

    transition_id = int(body.transition.get("id", 0))
    try:
        await workflow_service.execute_transition(
            db, issue, transition_id,
            author_id=current_user.id,
            fields=body.fields,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_jira_error([str(exc)]),
        )

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Watchers (stubs)
# ---------------------------------------------------------------------------


@router.get("/issue/{issueIdOrKey}/watchers")
async def get_watchers(
    issueIdOrKey: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get watchers for an issue."""
    settings = get_settings()
    base_url = settings.BASE_URL

    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )

    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Watcher)
        .options(selectinload(Watcher.user))
        .where(Watcher.issue_id == issue.id)
    )
    watchers = list(result.scalars().all())

    watcher_list = []
    for w in watchers:
        watcher_list.append(_format_user(w.user, base_url))

    return {
        "self": f"{base_url}/rest/api/2/issue/{issue.key}/watchers",
        "isWatching": any(w.user_id == current_user.id for w in watchers),
        "watchCount": len(watchers),
        "watchers": watcher_list,
    }


@router.post("/issue/{issueIdOrKey}/watchers", status_code=204)
async def add_watcher(
    issueIdOrKey: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a watcher to an issue. Body is a JSON string with the username."""
    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )

    # Body is a plain JSON string (e.g. "\"username\"")
    raw_body = await request.body()
    username = raw_body.decode("utf-8").strip().strip('"')
    if not username:
        username = current_user.username

    watcher_user = await get_or_create_user(db, username, username)

    # Check if already watching
    existing = await db.execute(
        select(Watcher).where(
            Watcher.issue_id == issue.id,
            Watcher.user_id == watcher_user.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(Watcher(issue_id=issue.id, user_id=watcher_user.id))
        await db.flush()

    return Response(status_code=204)


@router.delete("/issue/{issueIdOrKey}/watchers")
async def remove_watcher(
    issueIdOrKey: str,
    username: str = Query(...),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a watcher from an issue."""
    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue Does Not Exist: {issueIdOrKey}"]),
        )

    from jira_emulator.services.user_service import get_user_by_username

    watcher_user = await get_user_by_username(db, username)
    if watcher_user is None:
        return Response(status_code=204)

    result = await db.execute(
        select(Watcher).where(
            Watcher.issue_id == issue.id,
            Watcher.user_id == watcher_user.id,
        )
    )
    watcher = result.scalar_one_or_none()
    if watcher:
        await db.delete(watcher)
        await db.flush()

    return Response(status_code=204)
