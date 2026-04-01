"""Seed data loader for initial database population."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.models import (
    Component,
    CustomField,
    IssueLinkType,
    IssueSequence,
    IssueType,
    Priority,
    Project,
    ProjectIssueType,
    ProjectWorkflow,
    Resolution,
    Status,
    User,
    Workflow,
    WorkflowTransition,
)
from jira_emulator.services.auth_service import hash_password, hash_token

logger = logging.getLogger(__name__)

DEFAULT_API_TOKEN = "jira-emulator-default-token"

PROJECTS = [
    {"key": "RHAIRFE", "name": "Red Hat AI RFE project", "description": "Request for Enhancement tracking"},
    {"key": "RHAISTRAT", "name": "Red Hat AI Strategy", "description": "Features and Initiatives"},
    {"key": "RHOAIENG", "name": "Red Hat OpenShift AI Engineering", "description": "Engineering work items"},
    {"key": "AIPCC", "name": "AIPCC", "description": "AIPCC-specific work items"},
]

ISSUE_TYPES = [
    {"name": "Feature Request", "subtask": False},
    {"name": "Feature", "subtask": False},
    {"name": "Initiative", "subtask": False},
    {"name": "Bug", "subtask": False},
    {"name": "Task", "subtask": False},
    {"name": "Story", "subtask": False},
    {"name": "Epic", "subtask": False},
    {"name": "Sub-task", "subtask": True},
]

# Maps project key -> list of issue type names allowed
PROJECT_ISSUE_TYPES = {
    "RHAIRFE": ["Feature Request", "Sub-task"],
    "RHAISTRAT": ["Feature", "Initiative", "Sub-task"],
    "RHOAIENG": ["Bug", "Task", "Story", "Epic", "Sub-task"],
    "AIPCC": ["Bug", "Task", "Story", "Epic", "Sub-task"],
}

PRIORITIES = [
    {"name": "Blocker", "sort_order": 1},
    {"name": "Critical", "sort_order": 2},
    {"name": "Major", "sort_order": 3},
    {"name": "Normal", "sort_order": 4},
    {"name": "Minor", "sort_order": 5},
    {"name": "Undefined", "sort_order": 6},
]

STATUSES = [
    {"name": "New", "category": "new"},
    {"name": "Backlog", "category": "new"},
    {"name": "To Do", "category": "new"},
    {"name": "Stakeholder Review", "category": "indeterminate"},
    {"name": "Review", "category": "indeterminate"},
    {"name": "Refinement", "category": "indeterminate"},
    {"name": "Pending Approval", "category": "indeterminate"},
    {"name": "Rejection Pending", "category": "indeterminate"},
    {"name": "In Progress", "category": "indeterminate"},
    {"name": "Code Review", "category": "indeterminate"},
    {"name": "Testing", "category": "indeterminate"},
    {"name": "Approved", "category": "done"},
    {"name": "Done", "category": "done"},
    {"name": "Closed", "category": "done"},
]

RESOLUTIONS = [
    {"name": "Done"},
    {"name": "Won't Do"},
    {"name": "Duplicate"},
    {"name": "Cannot Reproduce"},
    {"name": "Incomplete"},
]

LINK_TYPES = [
    {"name": "Blocks", "inward_description": "is blocked by", "outward_description": "blocks"},
    {"name": "Cloners", "inward_description": "is cloned by", "outward_description": "clones"},
    {"name": "Duplicate", "inward_description": "is duplicated by", "outward_description": "duplicates"},
    {"name": "Relates", "inward_description": "relates to", "outward_description": "relates to"},
]

CUSTOM_FIELDS = [
    {"field_id": "customfield_12310243", "name": "Story Points", "field_type": "number"},
    {"field_id": "customfield_12313240", "name": "Team", "field_type": "string"},
    {"field_id": "customfield_12313941", "name": "Target Start", "field_type": "date"},
    {"field_id": "customfield_12313942", "name": "Target End", "field_type": "date"},
    {"field_id": "customfield_12310170", "name": "Affects Testing", "field_type": "multiselect"},
    {"field_id": "customfield_12319743", "name": "Release Blocker", "field_type": "select"},
    {"field_id": "customfield_12316142", "name": "Severity", "field_type": "select"},
]

# Workflow definitions: name -> list of (from_status_name | None, transition_name, to_status_name)
WORKFLOWS = {
    "RHAIRFE Workflow": [
        ("New", "Submit for Review", "Stakeholder Review"),
        ("Stakeholder Review", "Begin Review", "Review"),
        ("Review", "Accept", "Pending Approval"),
        ("Review", "Reject", "Rejection Pending"),
        ("Pending Approval", "Approve", "Approved"),
        ("Pending Approval", "Reopen", "Review"),
        ("Rejection Pending", "Close", "Closed"),
        ("Rejection Pending", "Reopen", "Review"),
        (None, "Close", "Closed"),  # global transition
    ],
    "RHAISTRAT Workflow": [
        ("New", "Start Refinement", "Refinement"),
        ("Refinement", "Start Progress", "In Progress"),
        ("In Progress", "Submit for Review", "Review"),
        ("Review", "Complete", "Done"),
        ("Review", "Reopen", "In Progress"),
        (None, "Close", "Closed"),
    ],
    "Default Workflow": [
        ("New", "Start", "To Do"),
        ("To Do", "Start Progress", "In Progress"),
        ("Backlog", "Start Progress", "In Progress"),
        ("In Progress", "Submit for Review", "Code Review"),
        ("Code Review", "Start Testing", "Testing"),
        ("Code Review", "Reopen", "In Progress"),
        ("Testing", "Complete", "Done"),
        ("Testing", "Reopen", "In Progress"),
        (None, "Close", "Closed"),
    ],
}

PROJECT_WORKFLOWS = {
    "RHAIRFE": "RHAIRFE Workflow",
    "RHAISTRAT": "RHAISTRAT Workflow",
    "RHOAIENG": "Default Workflow",
    "AIPCC": "Default Workflow",
}


async def is_db_seeded(db: AsyncSession) -> bool:
    """Check if the database already has seed data."""
    result = await db.execute(select(Project).limit(1))
    return result.scalar_one_or_none() is not None


async def load_seed_data(db: AsyncSession, admin_password: str = "admin") -> None:
    """Populate the database with initial reference data."""
    if await is_db_seeded(db):
        logger.info("Database already seeded, skipping")
        return

    logger.info("Loading seed data...")

    # Issue types
    issue_type_map: dict[str, IssueType] = {}
    for it_data in ISSUE_TYPES:
        it = IssueType(**it_data)
        db.add(it)
        issue_type_map[it.name] = it
    await db.flush()

    # Statuses
    status_map: dict[str, Status] = {}
    for s_data in STATUSES:
        s = Status(**s_data)
        db.add(s)
        status_map[s.name] = s
    await db.flush()

    # Priorities
    for p_data in PRIORITIES:
        db.add(Priority(**p_data))
    await db.flush()

    # Resolutions
    for r_data in RESOLUTIONS:
        db.add(Resolution(**r_data))
    await db.flush()

    # Link types
    for lt_data in LINK_TYPES:
        db.add(IssueLinkType(**lt_data))
    await db.flush()

    # Custom fields
    for cf_data in CUSTOM_FIELDS:
        db.add(CustomField(**cf_data))
    await db.flush()

    # Workflows + transitions
    workflow_map: dict[str, Workflow] = {}
    for wf_name, transitions in WORKFLOWS.items():
        wf = Workflow(name=wf_name)
        db.add(wf)
        await db.flush()
        workflow_map[wf_name] = wf

        for from_status_name, trans_name, to_status_name in transitions:
            from_status = status_map.get(from_status_name) if from_status_name else None
            to_status = status_map[to_status_name]
            wt = WorkflowTransition(
                workflow_id=wf.id,
                name=trans_name,
                from_status_id=from_status.id if from_status else None,
                to_status_id=to_status.id,
            )
            db.add(wt)
    await db.flush()

    # Projects
    project_map: dict[str, Project] = {}
    for p_data in PROJECTS:
        p = Project(**p_data)
        db.add(p)
        project_map[p.key] = p
    await db.flush()

    # Project -> issue type associations
    for proj_key, type_names in PROJECT_ISSUE_TYPES.items():
        proj = project_map[proj_key]
        for type_name in type_names:
            it = issue_type_map[type_name]
            db.add(ProjectIssueType(project_id=proj.id, issue_type_id=it.id))
    await db.flush()

    # Project -> workflow associations (default for all issue types)
    for proj_key, wf_name in PROJECT_WORKFLOWS.items():
        proj = project_map[proj_key]
        wf = workflow_map[wf_name]
        db.add(ProjectWorkflow(project_id=proj.id, issue_type_id=None, workflow_id=wf.id))
    await db.flush()

    # Issue sequences
    for proj in project_map.values():
        db.add(IssueSequence(project_id=proj.id, next_number=1))
    await db.flush()

    # Default admin user with hashed password
    admin = User(
        username="admin",
        display_name="Admin User",
        email="admin@example.com",
        password_hash=hash_password(admin_password),
    )
    db.add(admin)
    await db.flush()

    # Default API token
    from jira_emulator.models.api_token import ApiToken

    db.add(ApiToken(
        user_id=admin.id,
        name="Default Token",
        token_hash=hash_token(DEFAULT_API_TOKEN),
        token_prefix=DEFAULT_API_TOKEN[:8],
    ))

    await db.commit()
    logger.info("Seed data loaded successfully")
