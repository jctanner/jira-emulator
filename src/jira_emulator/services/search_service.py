"""Search service: JQL parsing, transformation, and execution.

Provides ``search_issues()`` which accepts a JQL string and returns a
Jira-compatible search response dict.
"""

from __future__ import annotations

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.models.issue import Issue
from jira_emulator.models.user import User
from jira_emulator.jql.parser import parse_jql
from jira_emulator.jql.transformer import JQLTransformer
from jira_emulator.services import issue_service


async def search_issues(
    db: AsyncSession,
    jql: str,
    start_at: int = 0,
    max_results: int = 50,
    fields_filter: list[str] | None = None,
    current_user: User | None = None,
    base_url: str = "",
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
        # Default ordering: by key ascending
        stmt = stmt.order_by(Issue.key.asc())

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
        )
        formatted_issues.append(formatted)

    return {
        "expand": "schema,names",
        "startAt": start_at,
        "maxResults": max_results,
        "total": total,
        "issues": formatted_issues,
    }
