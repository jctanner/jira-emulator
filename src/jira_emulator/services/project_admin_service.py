"""Admin project maintenance helpers."""

import re
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.models.attachment import Attachment
from jira_emulator.models.comment import Comment
from jira_emulator.models.component import Component, IssueComponent
from jira_emulator.models.custom_field import IssueCustomFieldValue
from jira_emulator.models.issue import Issue, IssueSequence
from jira_emulator.models.issue_history import IssueHistory
from jira_emulator.models.issue_type import IssueType
from jira_emulator.models.label import Label
from jira_emulator.models.link import IssueLink
from jira_emulator.models.project import Project, ProjectIssueType, ProjectWorkflow
from jira_emulator.models.remote_link import RemoteLink
from jira_emulator.models.sprint import IssueSprint
from jira_emulator.models.version import IssueAffectsVersion, IssueFixVersion, Version
from jira_emulator.models.watcher import Watcher
from jira_emulator.models.workflow import Workflow

PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*$")


@dataclass(frozen=True)
class ProjectMaintenanceResult:
    project: Project
    issues_deleted: int = 0


def normalize_project_key(key: str) -> str:
    """Return a normalized project key or raise ValueError."""
    normalized = key.strip().upper()
    if not normalized:
        raise ValueError("Project key is required")
    if not PROJECT_KEY_RE.fullmatch(normalized):
        raise ValueError("Project key must start with a letter and contain only uppercase letters and numbers")
    return normalized


async def create_project(
    db: AsyncSession,
    *,
    key: str,
    name: str,
    description: str | None = None,
    lead: str | None = None,
    project_type_key: str = "software",
) -> Project:
    """Create a project with default issue types, workflow, and sequence."""
    project_key = normalize_project_key(key)
    project_name = name.strip()
    if not project_name:
        raise ValueError("Project name is required")

    existing = (await db.execute(select(Project).where(func.upper(Project.key) == project_key))).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"Project {project_key} already exists")

    project = Project(
        key=project_key,
        name=project_name,
        description=description.strip() if description else None,
        lead=lead.strip() if lead else None,
        project_type_key=project_type_key.strip() or "software",
    )
    db.add(project)
    await db.flush()

    issue_types = (await db.execute(select(IssueType).order_by(IssueType.id))).scalars().all()
    for issue_type in issue_types:
        db.add(ProjectIssueType(project_id=project.id, issue_type_id=issue_type.id))

    workflow = (await db.execute(select(Workflow).order_by(Workflow.id).limit(1))).scalar_one_or_none()
    if workflow is not None:
        db.add(ProjectWorkflow(project_id=project.id, issue_type_id=None, workflow_id=workflow.id))

    db.add(IssueSequence(project_id=project.id, next_number=1))
    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, key_or_id: str) -> ProjectMaintenanceResult | None:
    """Delete a project and all issues/entities scoped to it."""
    stmt = select(Project)
    try:
        project_id = int(key_or_id)
    except ValueError:
        stmt = stmt.where(Project.key == key_or_id.upper())
    else:
        stmt = stmt.where(Project.id == project_id)

    project = (await db.execute(stmt)).scalar_one_or_none()
    if project is None:
        return None

    issue_ids = list((await db.execute(select(Issue.id).where(Issue.project_id == project.id))).scalars().all())
    version_ids = list((await db.execute(select(Version.id).where(Version.project_id == project.id))).scalars().all())
    component_ids = list(
        (await db.execute(select(Component.id).where(Component.project_id == project.id))).scalars().all()
    )

    if issue_ids:
        await db.execute(update(Issue).where(Issue.parent_id.in_(issue_ids)).values(parent_id=None))
        await db.execute(
            delete(IssueLink).where(
                or_(IssueLink.inward_issue_id.in_(issue_ids), IssueLink.outward_issue_id.in_(issue_ids))
            )
        )
        for model in (
            Label,
            Comment,
            IssueCustomFieldValue,
            Watcher,
            IssueSprint,
            IssueHistory,
            Attachment,
            RemoteLink,
        ):
            await db.execute(delete(model).where(model.issue_id.in_(issue_ids)))
        await db.execute(delete(IssueComponent).where(IssueComponent.issue_id.in_(issue_ids)))
        await db.execute(delete(IssueFixVersion).where(IssueFixVersion.issue_id.in_(issue_ids)))
        await db.execute(delete(IssueAffectsVersion).where(IssueAffectsVersion.issue_id.in_(issue_ids)))

    if component_ids:
        await db.execute(delete(IssueComponent).where(IssueComponent.component_id.in_(component_ids)))
    if version_ids:
        await db.execute(delete(IssueFixVersion).where(IssueFixVersion.version_id.in_(version_ids)))
        await db.execute(delete(IssueAffectsVersion).where(IssueAffectsVersion.version_id.in_(version_ids)))

    await db.execute(delete(Issue).where(Issue.project_id == project.id))
    await db.execute(delete(Component).where(Component.project_id == project.id))
    await db.execute(delete(Version).where(Version.project_id == project.id))
    await db.execute(delete(ProjectIssueType).where(ProjectIssueType.project_id == project.id))
    await db.execute(delete(ProjectWorkflow).where(ProjectWorkflow.project_id == project.id))
    await db.execute(delete(IssueSequence).where(IssueSequence.project_id == project.id))
    await db.delete(project)
    await db.commit()

    return ProjectMaintenanceResult(project=project, issues_deleted=len(issue_ids))
