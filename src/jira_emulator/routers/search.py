"""Search endpoints.

* ``/search`` (GET and POST): the legacy search, kept for jira-python and
  existing emulator clients. Offset pagination with ``total`` on v2; v3
  adds ``nextPageToken``/``isLast``. Jira Cloud removed it in 2025
  (CHANGE-2598).
* ``/search/jql`` (GET and POST): Jira Cloud's enhanced search, on v2 and
  v3 alike: cursor pagination, no ``total``, bounded JQL, ``id``-only
  fields by default.
* ``/search/approximate-count`` (POST).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.user import User
from jira_emulator.schemas.search import ApproximateCountRequest, SearchJqlRequest, SearchRequest
from jira_emulator.services import search_service

router = APIRouter(prefix="/rest/api/2")


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


def _get_api_version(request: Request) -> int:
    return getattr(request.state, "api_version", 2)


@router.post("/search")
async def search_issues_post(
    body: SearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Search for issues via JQL (POST, legacy)."""
    settings = get_settings()
    api_version = _get_api_version(request)
    try:
        return await search_service.search_issues(
            db,
            jql=body.jql,
            start_at=body.startAt,
            max_results=body.maxResults,
            fields_filter=body.fields,
            current_user=current_user,
            base_url=settings.BASE_URL,
            api_version=api_version,
            next_page_token=body.nextPageToken if api_version == 3 else None,
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
    nextPageToken: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Search for issues via JQL (GET, legacy)."""
    settings = get_settings()
    api_version = _get_api_version(request)

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
            api_version=api_version,
            next_page_token=nextPageToken if api_version == 3 else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_jira_error([str(exc)]),
        )


def _split_fields(values: list[str] | None) -> list[str] | None:
    """Flatten repeated and comma-separated ``fields`` values."""
    if not values:
        return None
    fields = [f.strip() for v in values for f in v.split(",") if f.strip()]
    return fields or None


async def _search_jql(request: Request, db: AsyncSession, current_user: User, **kwargs):
    # Invalid or unbounded JQL raises ValueError, which the app's handler
    # turns into Jira's 400 ``{"errorMessages": [...], "errors": {}}``.
    return await search_service.search_issues_jql(
        db,
        current_user=current_user,
        base_url=get_settings().BASE_URL,
        api_version=_get_api_version(request),
        **kwargs,
    )


@router.post("/search/jql")
async def search_jql_post(
    body: SearchJqlRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Jira Cloud enhanced search (POST), REST v2 and v3."""
    return await _search_jql(
        request,
        db,
        current_user,
        jql=body.jql,
        max_results=body.maxResults,
        fields_filter=_split_fields(body.fields),
        expand=body.expand,
        next_page_token=body.nextPageToken,
    )


@router.get("/search/jql")
async def search_jql_get(
    request: Request,
    jql: str = Query(default=""),
    nextPageToken: str | None = Query(default=None),
    maxResults: int = Query(default=50),
    fields: list[str] | None = Query(default=None),
    expand: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Jira Cloud enhanced search (GET), REST v2 and v3."""
    return await _search_jql(
        request,
        db,
        current_user,
        jql=jql,
        max_results=maxResults,
        fields_filter=_split_fields(fields),
        expand=expand,
        next_page_token=nextPageToken,
    )


@router.post("/search/approximate-count")
async def search_approximate_count(
    body: ApproximateCountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estimated number of issues matching bounded JQL: ``{"count": n}``."""
    return await search_service.approximate_count(db, body.jql, current_user)
