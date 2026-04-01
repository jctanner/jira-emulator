"""Project service: list and get operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jira_emulator.models.project import Project, ProjectIssueType
from jira_emulator.models.component import Component
from jira_emulator.models.version import Version


async def list_projects(db: AsyncSession) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.key))
    return list(result.scalars().all())


async def get_project(db: AsyncSession, key_or_id: str) -> Project | None:
    """Get project by key or numeric id."""
    stmt = select(Project).options(
        selectinload(Project.components),
        selectinload(Project.versions),
        selectinload(Project.issue_type_associations).selectinload(ProjectIssueType.issue_type),
    )
    # Try as key first
    result = await db.execute(stmt.where(Project.key == key_or_id))
    project = result.scalar_one_or_none()
    if project:
        return project

    # Try as numeric id
    try:
        pid = int(key_or_id)
        result = await db.execute(stmt.where(Project.id == pid))
        return result.scalar_one_or_none()
    except ValueError:
        return None
