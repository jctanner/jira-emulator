"""``POST /issue/bulkfetch``: fetch up to 100, or 1000, issues in one call.

Follows Jira Cloud's "Bulk fetch issues" operation, including CHANGE-3413
(2026-08-28), which raised the limit from 100 to 1000 issues for requests
that can be served efficiently. A request gets the 1000 limit only when:

- ``fields`` names at least one field to include, and at most 100 of them.
  Exclusions alone, ``*all``, ``*navigable`` and the default (``*navigable``)
  are not eligible;
- none of the included fields returns multiple values. Jira's examples are
  ``comment``, ``worklog`` and ``attachment``; and
- ``expand`` includes none of ``changelog``, ``editmeta``, ``operations``,
  ``renderedFields``, ``transitions`` or ``versionedRepresentations``.

Issues come back in ascending id order. Ids or keys that match no issue are
left out; they are not reported in ``issueErrors``.
"""

import json

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.models.issue import Issue
from jira_emulator.services import issue_service

DEFAULT_LIMIT = 100
EFFICIENT_LIMIT = 1000
MAX_EXPLICIT_FIELDS = 100
MAX_PROPERTIES = 5
MULTI_VALUE_FIELDS = frozenset({"comment", "worklog", "attachment"})
EXPENSIVE_EXPANDS = frozenset(
    {"changelog", "editmeta", "operations", "renderedfields", "transitions", "versionedrepresentations"}
)
WILDCARDS = frozenset({"*all", "*navigable"})


def _split(values: list[str] | None) -> list[str]:
    """Flatten a list whose entries may themselves be comma-separated."""
    return [part.strip() for value in values or [] for part in value.split(",") if part.strip()]


def issue_limit(fields: list[str], expand: list[str]) -> int:
    """Return how many issues this request shape may fetch."""
    includes = [f for f in fields if not f.startswith("-")]
    eligible = (
        bool(includes)
        and not WILDCARDS & set(includes)
        and len(includes) <= MAX_EXPLICIT_FIELDS
        and not MULTI_VALUE_FIELDS & {f.lower() for f in includes}
        and not EXPENSIVE_EXPANDS & {e.lower() for e in expand}
    )
    return EFFICIENT_LIMIT if eligible else DEFAULT_LIMIT


async def bulk_fetch(
    db: AsyncSession,
    *,
    issue_ids_or_keys: list[str] | None,
    fields: list[str] | None,
    expand: list[str] | None,
    properties: list[str] | None,
    base_url: str,
    api_version: int,
) -> dict:
    """Return Jira's ``BulkIssueResults``; raise ``ValueError`` for a 400."""
    requested = [str(v).strip() for v in issue_ids_or_keys or [] if str(v).strip()]
    field_list = _split(fields) or ["*navigable"]
    expand_list = _split(expand)
    property_keys = _split(properties)

    if not requested:
        raise ValueError("At least one issue ID or key must be provided in issueIdsOrKeys.")
    if len(property_keys) > MAX_PROPERTIES:
        raise ValueError(f"A maximum of {MAX_PROPERTIES} issue property keys can be specified.")
    limit = issue_limit(field_list, expand_list)
    if len(requested) > limit:
        if limit == DEFAULT_LIMIT and len(requested) <= EFFICIENT_LIMIT:
            raise ValueError(
                f"A maximum of {DEFAULT_LIMIT} issues can be requested for this combination of fields and expand. "
                f"To request up to {EFFICIENT_LIMIT} issues, list the fields explicitly (at most "
                f"{MAX_EXPLICIT_FIELDS}, none of comment, worklog or attachment) and don't expand changelog, "
                "editmeta, operations, renderedFields, transitions or versionedRepresentations."
            )
        raise ValueError(f"A maximum of {limit} issues can be requested.")

    ids = {int(v) for v in requested if v.isdigit()}
    keys = {v.upper() for v in requested if not v.isdigit()}
    conditions = []
    if ids:
        conditions.append(Issue.id.in_(ids))
    if keys:
        conditions.append(func.upper(Issue.key).in_(keys))
    stmt = select(Issue).options(*issue_service._issue_load_options()).where(or_(*conditions)).order_by(Issue.id)
    issues = (await db.execute(stmt)).scalars().unique().all()

    includes = [f for f in field_list if not f.startswith("-")] or ["*navigable"]
    excludes = {f[1:] for f in field_list if f.startswith("-")}
    # format_issue_response takes either one wildcard or explicit names.
    wildcard = next((f for f in includes if f in WILDCARDS), None)
    fields_filter = [wildcard] if wildcard else includes
    expand_set = {e.lower() for e in expand_list}

    results = []
    for issue in issues:
        data = await issue_service.format_issue_response(
            issue,
            base_url,
            db,
            fields_filter=fields_filter,
            api_version=api_version,
            expand=",".join(expand_list) or None,
        )
        for name in excludes:
            data["fields"].pop(name, None)
        if "changelog" not in expand_set:
            data.pop("changelog", None)
        data["expand"] = ""
        if property_keys:
            data["properties"] = {p.key: json.loads(p.value) for p in issue.properties if p.key in property_keys}
        results.append(data)

    return {
        "expand": ",".join(e for e in expand_list if e.lower() in {"names", "schema"}),
        "issues": results,
        "issueErrors": [],
    }
