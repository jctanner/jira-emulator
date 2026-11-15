"""Search service: JQL parsing, transformation, and execution.

Provides ``search_issues()`` which accepts a JQL string and returns a
Jira-compatible search response dict.
"""

from __future__ import annotations

import base64

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.jql.parser import parse_jql
from jira_emulator.jql.transformer import JQLTransformer
from jira_emulator.models.issue import Issue
from jira_emulator.models.user import User
from jira_emulator.services import issue_service


def encode_page_token(offset: int) -> str:
    """Encode an offset into an opaque nextPageToken."""
    return base64.b64encode(str(offset).encode()).decode()


def decode_page_token(token: str) -> int:
    """Decode a nextPageToken back into an offset."""
    try:
        return int(base64.b64decode(token).decode())
    except (ValueError, Exception):
        raise ValueError(f"Invalid nextPageToken: {token}")


async def search_issues(
    db: AsyncSession,
    jql: str,
    start_at: int = 0,
    max_results: int = 50,
    fields_filter: list[str] | None = None,
    current_user: User | None = None,
    base_url: str = "",
    api_version: int = 2,
    next_page_token: str | None = None,
) -> dict:
    """Execute a JQL search and return a Jira REST-style response dict.

    Parameters
    ----------
    db:
        Async database session.
    jql:
        The JQL query string (e.g. ``"project = DEMO AND status = Open"``).
    start_at:
        Zero-based offset for pagination.
    max_results:
        Maximum number of issues to return (capped at 1000).
    fields_filter:
        Optional list of field names to include in the response.
        ``None`` or ``["*all"]`` means return all fields.
    current_user:
        The authenticated user — passed through to JQL functions like
        ``currentUser()``.
    base_url:
        Base URL of the Jira emulator (used in ``self`` links).

    Returns
    -------
    dict
        A dict matching the Jira ``SearchResponse`` format::

            {
                "expand": "schema,names",
                "startAt": 0,
                "maxResults": 50,
                "total": 123,
                "issues": [...]
            }

    Raises
    ------
    ValueError
        If the JQL is syntactically invalid or references unknown fields.
    """
    max_results = min(max_results, 1000)
    if max_results < 0:
        max_results = 50

    # For v3, decode nextPageToken to get the offset
    if next_page_token is not None:
        start_at = decode_page_token(next_page_token)

    current_username = current_user.username if current_user else None

    # ---- Parse & Transform ----
    tree = parse_jql(jql)
    transformer = JQLTransformer()
    where_clauses, order_by_clauses = transformer.transform(tree, current_username)

    # ---- Count total matching issues ----
    count_stmt = select(sa_func.count()).select_from(Issue)
    if where_clauses:
        count_stmt = count_stmt.where(*where_clauses)

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # ---- Build the main query ----
    stmt = select(Issue).options(*issue_service._issue_load_options())

    if where_clauses:
        stmt = stmt.where(*where_clauses)

    if order_by_clauses:
        stmt = stmt.order_by(*order_by_clauses)
    else:
        # Default ordering: by key ascending, numerically within a project
        stmt = stmt.order_by(*(part.asc() for part in JQLTransformer._KEY_ORDER))

    # Pagination
    stmt = stmt.offset(start_at).limit(max_results)

    result = await db.execute(stmt)
    issues = list(result.scalars().unique().all())

    # ---- Format responses ----
    formatted_issues = []
    for iss in issues:
        formatted = await issue_service.format_issue_response(
            issue=iss,
            base_url=base_url,
            db=db,
            fields_filter=fields_filter,
            api_version=api_version,
        )
        formatted_issues.append(formatted)

    if api_version == 3:
        next_offset = start_at + len(formatted_issues)
        is_last = next_offset >= total
        response = {
            "expand": "schema,names",
            "maxResults": max_results,
            "total": total,
            "isLast": is_last,
            "issues": formatted_issues,
        }
        if not is_last:
            response["nextPageToken"] = encode_page_token(next_offset)
        return response

    return {
        "expand": "schema,names",
        "startAt": start_at,
        "maxResults": max_results,
        "total": total,
        "issues": formatted_issues,
    }


# ---------------------------------------------------------------------------
# Jira Cloud enhanced search: /search/jql and /search/approximate-count
# ---------------------------------------------------------------------------

UNBOUNDED_JQL_MESSAGE = "Unbounded JQL queries are not allowed here. Please add a search restriction to your query."

# Jira Cloud returns at most 5000 issues per page when only ids or keys are
# requested; the emulator keeps its general 1000 cap for richer requests.
_ID_ONLY_PAGE_CAP = 5000
_PAGE_CAP = 1000


def _bounded_where(jql: str, current_username: str | None) -> tuple[list, list]:
    """Parse *jql*, rejecting empty or ORDER BY-only (unbounded) queries."""
    if not jql or not jql.strip():
        raise ValueError(UNBOUNDED_JQL_MESSAGE)
    tree = parse_jql(jql)
    where_clauses, order_by_clauses = JQLTransformer().transform(tree, current_username)
    if not where_clauses:
        raise ValueError(UNBOUNDED_JQL_MESSAGE)
    return where_clauses, order_by_clauses


async def search_issues_jql(
    db: AsyncSession,
    jql: str,
    max_results: int = 50,
    fields_filter: list[str] | None = None,
    expand: str | None = None,
    current_user: User | None = None,
    base_url: str = "",
    api_version: int = 2,
    next_page_token: str | None = None,
) -> dict:
    """Execute a Jira Cloud ``/search/jql`` request (REST v2 and v3).

    Unlike the legacy ``/search``, the response is cursor-paginated on both
    API versions and has no ``total``, ``startAt`` or ``maxResults``; the
    JQL must be bounded; and ``fields`` defaults to ``id`` only.
    """
    fields = fields_filter or ["id"]
    id_only = all(f in ("id", "key") for f in fields)
    if max_results is None or max_results <= 0:
        max_results = 50
    max_results = min(max_results, _ID_ONLY_PAGE_CAP if id_only else _PAGE_CAP)
    start_at = decode_page_token(next_page_token) if next_page_token else 0

    current_username = current_user.username if current_user else None
    where_clauses, order_by_clauses = _bounded_where(jql, current_username)

    stmt = select(Issue).options(*issue_service._issue_load_options()).where(*where_clauses)
    if order_by_clauses:
        stmt = stmt.order_by(*order_by_clauses)
    else:
        # Same default as the legacy search: key, by project then number.
        stmt = stmt.order_by(*(part.asc() for part in JQLTransformer._KEY_ORDER))
    # Fetch one extra row to learn whether another page exists.
    stmt = stmt.offset(start_at).limit(max_results + 1)
    rows = list((await db.execute(stmt)).scalars().unique().all())
    is_last = len(rows) <= max_results
    page = rows[:max_results]

    issues = []
    for iss in page:
        if fields == ["id"]:
            issues.append({"id": str(iss.id)})
            continue
        issues.append(
            await issue_service.format_issue_response(
                issue=iss,
                base_url=base_url,
                db=db,
                fields_filter=fields,
                api_version=api_version,
                expand=expand,
            )
        )

    response: dict = {"issues": issues, "isLast": is_last}
    if not is_last:
        response["nextPageToken"] = encode_page_token(start_at + len(page))
    return response


async def approximate_count(db: AsyncSession, jql: str, current_user: User | None = None) -> dict:
    """``POST /search/approximate-count``: ``{"count": n}`` for bounded JQL."""
    current_username = current_user.username if current_user else None
    where_clauses, _ = _bounded_where(jql, current_username)
    count = (await db.execute(select(sa_func.count()).select_from(Issue).where(*where_clauses))).scalar_one()
    return {"count": count}
