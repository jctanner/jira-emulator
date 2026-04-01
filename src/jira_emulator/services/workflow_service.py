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
    db: AsyncSession, issue: Issue, transition_id: int
) -> None:
    """Execute a workflow transition on *issue*.

    Raises ``ValueError`` if the transition is not valid for the issue's
    current workflow and status.

    Side-effects on the issue:
    * ``status_id`` is set to the transition's ``to_status_id``.
    * If the target status category is ``"done"``:
      - ``resolution_id`` is set to the ``Resolution`` named ``"Done"``.
      - ``resolved_at`` is set to the current time.
    * If the target status category is **not** ``"done"``:
      - ``resolution_id`` and ``resolved_at`` are cleared.
    * ``updated_at`` is refreshed.
    """

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

    # Update status
    issue.status_id = transition.to_status_id

    # Handle resolution based on target status category
    target_status = transition.to_status
    if target_status.category == "done":
        # Auto-resolve: look up the "Done" resolution
        res_result = await db.execute(
            select(Resolution).where(Resolution.name == "Done")
        )
        done_resolution = res_result.scalar_one_or_none()
        if done_resolution is not None:
            issue.resolution_id = done_resolution.id
        issue.resolved_at = now
    else:
        # Moving away from done — clear resolution
        issue.resolution_id = None
        issue.resolved_at = None

    issue.updated_at = now
