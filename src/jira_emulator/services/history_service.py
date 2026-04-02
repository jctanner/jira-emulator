"""History service: record and retrieve issue change history."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jira_emulator.models.issue_history import IssueHistory


async def record_change(
    db: AsyncSession,
    issue_id: int,
    author_id: int | None,
    field: str,
    old_value: str | None,
    old_id: str | None,
    new_value: str | None,
    new_id: str | None,
    field_type: str = "jira",
) -> IssueHistory:
    """Create an IssueHistory row for a single field change."""
    entry = IssueHistory(
        issue_id=issue_id,
        author_id=author_id,
        field=field,
        field_type=field_type,
        from_value=old_value,
        from_id=old_id,
        to_value=new_value,
        to_id=new_id,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    return entry


async def get_issue_history(
    db: AsyncSession, issue_id: int
) -> list[IssueHistory]:
    """Return all history entries for an issue, ordered by created_at ASC."""
    result = await db.execute(
        select(IssueHistory)
        .options(selectinload(IssueHistory.author))
        .where(IssueHistory.issue_id == issue_id)
        .order_by(IssueHistory.created_at.asc(), IssueHistory.id.asc())
    )
    return list(result.scalars().all())
