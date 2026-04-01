"""Search endpoints: /rest/api/2/search (GET and POST)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.user import User
from jira_emulator.schemas.search import SearchRequest
from jira_emulator.services import search_service

router = APIRouter(prefix="/rest/api/2")


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


@router.post("/search")
async def search_issues_post(
    body: SearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for issues via JQL (POST)."""
    settings = get_settings()
    try:
        return await search_service.search_issues(
            db,
            jql=body.jql,
            start_at=body.startAt,
            max_results=body.maxResults,
            fields_filter=body.fields,
            current_user=current_user,
            base_url=settings.BASE_URL,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_jira_error([str(exc)]),
        )


@router.get("/search")
async def search_issues_get(
    request: Request,
    jql: str = Query(default=""),
    startAt: int = Query(default=0),
    maxResults: int = Query(default=50),
    fields: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for issues via JQL (GET)."""
    settings = get_settings()

    fields_filter = None
    if fields:
        fields_filter = [f.strip() for f in fields.split(",")]

    try:
        return await search_service.search_issues(
            db,
            jql=jql,
            start_at=startAt,
            max_results=maxResults,
            fields_filter=fields_filter,
            current_user=current_user,
            base_url=settings.BASE_URL,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_jira_error([str(exc)]),
        )
