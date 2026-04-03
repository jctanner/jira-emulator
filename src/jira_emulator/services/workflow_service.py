"""Workflow service: transition lookup and execution."""

from datetime import datetime

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jira_emulator.models.issue import Issue
from jira_emulator.models.project import ProjectWorkflow
from jira_emulator.models.workflow import Workflow, WorkflowTransition
from jira_emulator.models.status import Status
from jira_emulator.models.resolution import Resolution


# ---------------------------------------------------------------------------
# get_workflow_for_issue
# ---------------------------------------------------------------------------

async def get_workflow_for_issue(db: AsyncSession, issue: Issue) -> Workflow | None:
    """Return the workflow governing *issue*.

    Resolution order:
    1. ``ProjectWorkflow`` with matching (project_id, issue_type_id) — specific.
    2. ``ProjectWorkflow`` with matching project_id and ``issue_type_id IS NULL``
       — default for the project.
    3. ``None`` when no mapping exists.
    """

    # 1. Specific match: project + issue type
    result = await db.execute(
        select(ProjectWorkflow)
        .options(selectinload(ProjectWorkflow.workflow))
        .where(
            ProjectWorkflow.project_id == issue.project_id,
            ProjectWorkflow.issue_type_id == issue.issue_type_id,
        )
    )
    pw = result.scalar_one_or_none()
    if pw is not None:
        return pw.workflow

    # 2. Fallback: project-level default (issue_type_id IS NULL)
    result = await db.execute(
        select(ProjectWorkflow)
        .options(selectinload(ProjectWorkflow.workflow))
        .where(
            ProjectWorkflow.project_id == issue.project_id,
            ProjectWorkflow.issue_type_id.is_(None),
        )
    )
    pw = result.scalar_one_or_none()
    if pw is not None:
        return pw.workflow

    return None


# ---------------------------------------------------------------------------
# get_available_transitions
# ---------------------------------------------------------------------------

async def get_available_transitions(
    db: AsyncSession, issue: Issue
) -> list[WorkflowTransition]:
    """Return every transition available from the issue's current status.

    A transition matches when:
    * Its ``workflow_id`` equals the issue's workflow, **and**
    * Its ``from_status_id`` equals ``issue.status_id`` (normal transition)
      **or** ``from_status_id IS NULL`` (global transition).
    """

    workflow = await get_workflow_for_issue(db, issue)
    if workflow is None:
        return []

    result = await db.execute(
        select(WorkflowTransition)
        .options(selectinload(WorkflowTransition.to_status))
        .where(
            WorkflowTransition.workflow_id == workflow.id,
            or_(
                WorkflowTransition.from_status_id == issue.status_id,
                WorkflowTransition.from_status_id.is_(None),
            ),
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# execute_transition
# ---------------------------------------------------------------------------

async def execute_transition(
    db: AsyncSession, issue: Issue, transition_id: int,
    author_id: int | None = None,
    fields: dict | None = None,
) -> None:
    """Execute a workflow transition on *issue*.

    Raises ``ValueError`` if the transition is not valid for the issue's
    current workflow and status.

    *fields* is an optional dict of field overrides from the transition
    request body.  If ``fields`` contains a ``resolution`` key, the
    specified resolution is used instead of the auto-default ``"Done"``.

    Side-effects on the issue:
    * ``status_id`` is set to the transition's ``to_status_id``.
    * If the target status category is ``"done"``:
      - ``resolution_id`` is set to the resolution specified in *fields*,
        or to ``"Done"`` if not provided.
      - ``resolved_at`` is set to the current time.
    * If the target status category is **not** ``"done"``:
      - ``resolution_id`` and ``resolved_at`` are cleared.
    * ``updated_at`` is refreshed.
    """

    from jira_emulator.services import history_service

    workflow = await get_workflow_for_issue(db, issue)
    if workflow is None:
        raise ValueError("No workflow configured for this issue")

    # Fetch the requested transition, eagerly loading to_status
    result = await db.execute(
        select(WorkflowTransition)
        .options(selectinload(WorkflowTransition.to_status))
        .where(
            WorkflowTransition.id == transition_id,
            WorkflowTransition.workflow_id == workflow.id,
            or_(
                WorkflowTransition.from_status_id == issue.status_id,
                WorkflowTransition.from_status_id.is_(None),
            ),
        )
    )
    transition = result.scalar_one_or_none()

    if transition is None:
        raise ValueError(
            f"Transition {transition_id} is not valid for issue "
            f"{issue.key} in status {issue.status_id}"
        )

    now = datetime.utcnow()

    # Capture old values for history
    old_status_name = issue.status.name if issue.status else None
    old_status_id = str(issue.status_id) if issue.status_id else None
    old_resolution_name = issue.resolution.name if issue.resolution else None
    old_resolution_id = str(issue.resolution_id) if issue.resolution_id else None

    # Update status
    issue.status_id = transition.to_status_id

    # Record status change
    target_status = transition.to_status
    await history_service.record_change(
        db, issue.id, author_id, "status",
        old_status_name, old_status_id,
        target_status.name, str(target_status.id),
    )

    # Handle resolution based on target status category
    if target_status.category == "done":
        # Determine resolution: use explicit override from fields, else "Done"
        resolution_name = "Done"
        if fields and "resolution" in fields:
            res_data = fields["resolution"]
            if isinstance(res_data, dict) and res_data.get("name"):
                resolution_name = res_data["name"]

        res_result = await db.execute(
            select(Resolution).where(Resolution.name == resolution_name)
        )
        resolution = res_result.scalar_one_or_none()

        # Fallback to "Done" if the requested resolution doesn't exist
        if resolution is None and resolution_name != "Done":
            res_result = await db.execute(
                select(Resolution).where(Resolution.name == "Done")
            )
            resolution = res_result.scalar_one_or_none()

        if resolution is not None:
            issue.resolution_id = resolution.id
            if old_resolution_name != resolution.name:
                await history_service.record_change(
                    db, issue.id, author_id, "resolution",
                    old_resolution_name, old_resolution_id,
                    resolution.name, str(resolution.id),
                )
        issue.resolved_at = now
    else:
        # Moving away from done — clear resolution
        issue.resolution_id = None
        issue.resolved_at = None
        if old_resolution_name is not None:
            await history_service.record_change(
                db, issue.id, author_id, "resolution",
                old_resolution_name, old_resolution_id, None, None,
            )

    issue.updated_at = now
