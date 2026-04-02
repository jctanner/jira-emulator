"""Issue service: CRUD operations and Jira-format response building."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jira_emulator.models.issue import Issue, IssueSequence
from jira_emulator.models.project import Project, ProjectWorkflow
from jira_emulator.models.issue_type import IssueType
from jira_emulator.models.status import Status
from jira_emulator.models.priority import Priority
from jira_emulator.models.resolution import Resolution
from jira_emulator.models.user import User
from jira_emulator.models.label import Label
from jira_emulator.models.component import Component, IssueComponent
from jira_emulator.models.version import Version, IssueFixVersion, IssueAffectsVersion
from jira_emulator.models.custom_field import CustomField, IssueCustomFieldValue
from jira_emulator.models.comment import Comment
from jira_emulator.models.link import IssueLink, IssueLinkType
from jira_emulator.models.watcher import Watcher
from jira_emulator.models.workflow import Workflow, WorkflowTransition
from jira_emulator.services import user_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_datetime(dt: datetime | None) -> str | None:
    """Format a datetime as Jira-style ``2026-01-15T10:30:00.000+0000``."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}+0000"


def _format_user(user: User | None, base_url: str) -> dict | None:
    """Return a Jira UserRef dict or ``None``."""
    if user is None:
        return None
    return {
        "self": f"{base_url}/rest/api/2/user?username={user.username}",
        "name": user.username,
        "key": user.username,
        "emailAddress": user.email or "",
        "displayName": user.display_name,
        "active": user.active,
        "timeZone": "UTC",
    }


def _status_category_for(category: str) -> dict:
    """Map a Status.category value to Jira's statusCategory object."""
    mapping = {
        "new": {"self": "", "id": 2, "key": "new", "colorName": "blue-gray", "name": "To Do"},
        "indeterminate": {"self": "", "id": 4, "key": "indeterminate", "colorName": "yellow", "name": "In Progress"},
        "done": {"self": "", "id": 3, "key": "done", "colorName": "green", "name": "Done"},
    }
    return mapping.get(category, mapping["new"])


# ---------------------------------------------------------------------------
# Eager-loading helper
# ---------------------------------------------------------------------------

def _issue_load_options():
    """Return selectinload options that eagerly fetch every Issue relationship."""
    return [
        selectinload(Issue.project),
        selectinload(Issue.status),
        selectinload(Issue.priority),
        selectinload(Issue.issue_type),
        selectinload(Issue.assignee),
        selectinload(Issue.reporter),
        selectinload(Issue.resolution),
        selectinload(Issue.parent),
        selectinload(Issue.labels),
        selectinload(Issue.comments).selectinload(Comment.author),
        selectinload(Issue.component_associations).selectinload(IssueComponent.component),
        selectinload(Issue.fix_version_associations).selectinload(IssueFixVersion.version),
        selectinload(Issue.affects_version_associations).selectinload(IssueAffectsVersion.version),
        selectinload(Issue.custom_field_values).selectinload(IssueCustomFieldValue.custom_field),
        selectinload(Issue.watchers).selectinload(Watcher.user),
        selectinload(Issue.outward_links).selectinload(IssueLink.link_type),
        selectinload(Issue.outward_links).selectinload(IssueLink.inward_issue),
        selectinload(Issue.inward_links).selectinload(IssueLink.link_type),
        selectinload(Issue.inward_links).selectinload(IssueLink.outward_issue),
    ]


# ---------------------------------------------------------------------------
# get_issue
# ---------------------------------------------------------------------------

async def get_issue(db: AsyncSession, issue_id_or_key: str) -> Issue | None:
    """Retrieve a single issue by key (e.g. ``RHAIRFE-42``) or numeric id."""
    stmt = select(Issue).options(*_issue_load_options())

    if "-" in str(issue_id_or_key):
        result = await db.execute(stmt.where(Issue.key == issue_id_or_key))
        return result.scalar_one_or_none()

    try:
        numeric_id = int(issue_id_or_key)
        result = await db.execute(stmt.where(Issue.id == numeric_id))
        return result.scalar_one_or_none()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# create_issue
# ---------------------------------------------------------------------------

async def create_issue(
    db: AsyncSession,
    fields: dict,
    current_user: User,
) -> Issue:
    """Create a new issue from the Jira-style *fields* dict.

    Raises ``ValueError`` when the project or issue type cannot be resolved.
    """

    # -- project --
    project_data = fields.get("project", {})
    project_key = project_data.get("key")
    if not project_key:
        raise ValueError("fields.project.key is required")

    result = await db.execute(select(Project).where(Project.key == project_key))
    project = result.scalar_one_or_none()
    if project is None:
        raise ValueError(f"Project '{project_key}' not found")

    # -- issue type --
    issue_type_data = fields.get("issuetype", {})
    issue_type_name = issue_type_data.get("name")
    if not issue_type_name:
        raise ValueError("fields.issuetype.name is required")

    result = await db.execute(select(IssueType).where(IssueType.name == issue_type_name))
    issue_type = result.scalar_one_or_none()
    if issue_type is None:
        raise ValueError(f"Issue type '{issue_type_name}' not found")

    # -- allocate key --
    result = await db.execute(
        select(IssueSequence).where(IssueSequence.project_id == project.id)
    )
    seq = result.scalar_one_or_none()
    if seq is None:
        seq = IssueSequence(project_id=project.id, next_number=1)
        db.add(seq)
        await db.flush()

    issue_number = seq.next_number
    seq.next_number = issue_number + 1
    issue_key = f"{project.key}-{issue_number}"

    # -- assignee --
    assignee: User | None = None
    assignee_data = fields.get("assignee")
    if assignee_data and assignee_data.get("name"):
        assignee = await user_service.get_or_create_user(
            db,
            display_name=assignee_data.get("displayName") or assignee_data["name"],
            username=assignee_data["name"],
        )

    # -- reporter --
    reporter: User = current_user
    reporter_data = fields.get("reporter")
    if reporter_data and reporter_data.get("name"):
        reporter = await user_service.get_or_create_user(
            db,
            display_name=reporter_data.get("displayName") or reporter_data["name"],
            username=reporter_data["name"],
        )

    # -- priority --
    priority: Priority | None = None
    priority_data = fields.get("priority")
    if priority_data and priority_data.get("name"):
        result = await db.execute(
            select(Priority).where(Priority.name == priority_data["name"])
        )
        priority = result.scalar_one_or_none()

    # -- initial status (via project workflow) --
    status: Status | None = None

    # Look up the project's workflow association
    # First try specific issue type, then fallback to default (issue_type_id IS NULL)
    result = await db.execute(
        select(ProjectWorkflow)
        .options(
            selectinload(ProjectWorkflow.workflow).selectinload(Workflow.transitions).selectinload(WorkflowTransition.from_status),
        )
        .where(
            ProjectWorkflow.project_id == project.id,
            (ProjectWorkflow.issue_type_id == issue_type.id)
            | (ProjectWorkflow.issue_type_id.is_(None)),
        )
        .order_by(ProjectWorkflow.issue_type_id.desc())  # prefer specific match
    )
    pw = result.scalars().first()

    if pw and pw.workflow and pw.workflow.transitions:
        # Find the first transition that has a from_status (i.e. the initial state)
        for t in pw.workflow.transitions:
            if t.from_status is not None:
                status = t.from_status
                break

    if status is None:
        # Fallback: look up a status named "New"
        result = await db.execute(select(Status).where(Status.name == "New"))
        status = result.scalar_one_or_none()

    if status is None:
        raise ValueError("Cannot determine initial status for issue")

    # -- parent --
    parent_id: int | None = None
    parent_data = fields.get("parent")
    if parent_data and parent_data.get("key"):
        parent_issue = await get_issue(db, parent_data["key"])
        if parent_issue:
            parent_id = parent_issue.id

    # -- build Issue --
    now = datetime.utcnow()
    issue = Issue(
        key=issue_key,
        project_id=project.id,
        issue_type_id=issue_type.id,
        summary=fields.get("summary", ""),
        description=fields.get("description"),
        status_id=status.id,
        priority_id=priority.id if priority else None,
        assignee_id=assignee.id if assignee else None,
        reporter_id=reporter.id if reporter else None,
        parent_id=parent_id,
        created_at=now,
        updated_at=now,
    )
    db.add(issue)
    await db.flush()  # get issue.id

    # -- labels --
    for label_text in fields.get("labels", []):
        db.add(Label(issue_id=issue.id, label=label_text))

    # -- components --
    for comp_data in fields.get("components", []):
        comp_name = comp_data.get("name")
        if not comp_name:
            continue
        # Look up existing component on the project
        result = await db.execute(
            select(Component).where(
                Component.project_id == project.id,
                Component.name == comp_name,
            )
        )
        component = result.scalar_one_or_none()
        if component is None:
            component = Component(project_id=project.id, name=comp_name)
            db.add(component)
            await db.flush()
        db.add(IssueComponent(issue_id=issue.id, component_id=component.id))

    # -- fix versions --
    for fv_data in fields.get("fixVersions", []):
        fv_name = fv_data.get("name")
        if not fv_name:
            continue
        result = await db.execute(
            select(Version).where(
                Version.project_id == project.id,
                Version.name == fv_name,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            version = Version(project_id=project.id, name=fv_name)
            db.add(version)
            await db.flush()
        db.add(IssueFixVersion(issue_id=issue.id, version_id=version.id))

    # -- affects versions --
    for av_data in fields.get("versions", []):
        av_name = av_data.get("name")
        if not av_name:
            continue
        result = await db.execute(
            select(Version).where(
                Version.project_id == project.id,
                Version.name == av_name,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            version = Version(project_id=project.id, name=av_name)
            db.add(version)
            await db.flush()
        db.add(IssueAffectsVersion(issue_id=issue.id, version_id=version.id))

    # -- custom fields --
    for field_key, field_value in fields.items():
        if not field_key.startswith("customfield_"):
            continue
        result = await db.execute(
            select(CustomField).where(CustomField.field_id == field_key)
        )
        cf = result.scalar_one_or_none()
        if cf is None:
            continue

        cfv = IssueCustomFieldValue(issue_id=issue.id, custom_field_id=cf.id)

        if cf.field_type == "number":
            try:
                cfv.value_number = float(field_value) if field_value is not None else None
            except (TypeError, ValueError):
                cfv.value_string = str(field_value)
        elif cf.field_type == "date":
            cfv.value_string = str(field_value) if field_value is not None else None
        elif cf.field_type in ("select", "multiselect"):
            # select/multiselect values come as dicts or lists of dicts
            import json
            if isinstance(field_value, (dict, list)):
                cfv.value_json = json.dumps(field_value)
            else:
                cfv.value_string = str(field_value) if field_value is not None else None
        else:
            cfv.value_string = str(field_value) if field_value is not None else None

        db.add(cfv)

    await db.flush()
    return issue


# ---------------------------------------------------------------------------
# update_issue
# ---------------------------------------------------------------------------

async def update_issue(
    db: AsyncSession,
    issue_id_or_key: str,
    fields: dict | None = None,
    update_ops: dict | None = None,
) -> Issue:
    """Update an existing issue.

    *fields* is a dict of field-name -> new-value (full replacement).
    *update_ops* follows the Jira ``update`` payload semantics (add/remove/set).

    Raises ``ValueError`` if the issue is not found.
    """
    issue = await get_issue(db, issue_id_or_key)
    if issue is None:
        raise ValueError(f"Issue '{issue_id_or_key}' not found")

    if fields:
        await _apply_field_updates(db, issue, fields)

    if update_ops:
        await _apply_update_ops(db, issue, update_ops)

    issue.updated_at = datetime.utcnow()
    await db.flush()
    return issue


async def _apply_field_updates(db: AsyncSession, issue: Issue, fields: dict) -> None:
    """Apply simple field-level updates to *issue*."""

    if "summary" in fields:
        issue.summary = fields["summary"]

    if "description" in fields:
        issue.description = fields["description"]

    # priority
    if "priority" in fields:
        priority_data = fields["priority"]
        if priority_data and priority_data.get("name"):
            result = await db.execute(
                select(Priority).where(Priority.name == priority_data["name"])
            )
            priority = result.scalar_one_or_none()
            if priority:
                issue.priority_id = priority.id
        else:
            issue.priority_id = None

    # assignee
    if "assignee" in fields:
        assignee_data = fields["assignee"]
        if assignee_data and assignee_data.get("name"):
            assignee = await user_service.get_or_create_user(
                db,
                display_name=assignee_data.get("displayName") or assignee_data["name"],
                username=assignee_data["name"],
            )
            issue.assignee_id = assignee.id
        else:
            issue.assignee_id = None

    # reporter
    if "reporter" in fields:
        reporter_data = fields["reporter"]
        if reporter_data and reporter_data.get("name"):
            reporter = await user_service.get_or_create_user(
                db,
                display_name=reporter_data.get("displayName") or reporter_data["name"],
                username=reporter_data["name"],
            )
            issue.reporter_id = reporter.id

    # resolution
    if "resolution" in fields:
        resolution_data = fields["resolution"]
        if resolution_data and resolution_data.get("name"):
            result = await db.execute(
                select(Resolution).where(Resolution.name == resolution_data["name"])
            )
            resolution = result.scalar_one_or_none()
            if resolution:
                issue.resolution_id = resolution.id
                issue.resolved_at = datetime.utcnow()
        else:
            issue.resolution_id = None
            issue.resolved_at = None

    # labels (full replacement)
    if "labels" in fields:
        # Delete existing labels
        for lbl in list(issue.labels):
            await db.delete(lbl)
        await db.flush()
        for label_text in fields["labels"]:
            db.add(Label(issue_id=issue.id, label=label_text))

    # components (full replacement)
    if "components" in fields:
        for ca in list(issue.component_associations):
            await db.delete(ca)
        await db.flush()
        for comp_data in fields["components"]:
            comp_name = comp_data.get("name")
            if not comp_name:
                continue
            result = await db.execute(
                select(Component).where(
                    Component.project_id == issue.project_id,
                    Component.name == comp_name,
                )
            )
            component = result.scalar_one_or_none()
            if component is None:
                component = Component(project_id=issue.project_id, name=comp_name)
                db.add(component)
                await db.flush()
            db.add(IssueComponent(issue_id=issue.id, component_id=component.id))

    # fixVersions (full replacement)
    if "fixVersions" in fields:
        for fva in list(issue.fix_version_associations):
            await db.delete(fva)
        await db.flush()
        for fv_data in fields["fixVersions"]:
            fv_name = fv_data.get("name")
            if not fv_name:
                continue
            result = await db.execute(
                select(Version).where(
                    Version.project_id == issue.project_id,
                    Version.name == fv_name,
                )
            )
            version = result.scalar_one_or_none()
            if version is None:
                version = Version(project_id=issue.project_id, name=fv_name)
                db.add(version)
                await db.flush()
            db.add(IssueFixVersion(issue_id=issue.id, version_id=version.id))

    # affects versions (full replacement)
    if "versions" in fields:
        for ava in list(issue.affects_version_associations):
            await db.delete(ava)
        await db.flush()
        for av_data in fields["versions"]:
            av_name = av_data.get("name")
            if not av_name:
                continue
            result = await db.execute(
                select(Version).where(
                    Version.project_id == issue.project_id,
                    Version.name == av_name,
                )
            )
            version = result.scalar_one_or_none()
            if version is None:
                version = Version(project_id=issue.project_id, name=av_name)
                db.add(version)
                await db.flush()
            db.add(IssueAffectsVersion(issue_id=issue.id, version_id=version.id))

    # custom fields
    for field_key, field_value in fields.items():
        if not field_key.startswith("customfield_"):
            continue
        result = await db.execute(
            select(CustomField).where(CustomField.field_id == field_key)
        )
        cf = result.scalar_one_or_none()
        if cf is None:
            continue

        # Find existing value or create new
        result = await db.execute(
            select(IssueCustomFieldValue).where(
                IssueCustomFieldValue.issue_id == issue.id,
                IssueCustomFieldValue.custom_field_id == cf.id,
            )
        )
        cfv = result.scalar_one_or_none()
        if cfv is None:
            cfv = IssueCustomFieldValue(issue_id=issue.id, custom_field_id=cf.id)
            db.add(cfv)

        # Clear all value columns first
        cfv.value_string = None
        cfv.value_number = None
        cfv.value_date = None
        cfv.value_json = None

        if field_value is not None:
            if cf.field_type == "number":
                try:
                    cfv.value_number = float(field_value)
                except (TypeError, ValueError):
                    cfv.value_string = str(field_value)
            elif cf.field_type == "date":
                cfv.value_string = str(field_value)
            elif cf.field_type in ("select", "multiselect"):
                import json
                if isinstance(field_value, (dict, list)):
                    cfv.value_json = json.dumps(field_value)
                else:
                    cfv.value_string = str(field_value)
            else:
                cfv.value_string = str(field_value)


async def _apply_update_ops(db: AsyncSession, issue: Issue, update_ops: dict) -> None:
    """Apply Jira ``update``-style operations (add/remove/set)."""

    # labels
    if "labels" in update_ops:
        for op in update_ops["labels"]:
            if "add" in op:
                db.add(Label(issue_id=issue.id, label=op["add"]))
            elif "remove" in op:
                for lbl in list(issue.labels):
                    if lbl.label == op["remove"]:
                        await db.delete(lbl)
            elif "set" in op:
                for lbl in list(issue.labels):
                    await db.delete(lbl)
                await db.flush()
                for label_text in op["set"]:
                    db.add(Label(issue_id=issue.id, label=label_text))

    # components
    if "components" in update_ops:
        for op in update_ops["components"]:
            if "add" in op:
                comp_name = op["add"].get("name") if isinstance(op["add"], dict) else op["add"]
                if comp_name:
                    result = await db.execute(
                        select(Component).where(
                            Component.project_id == issue.project_id,
                            Component.name == comp_name,
                        )
                    )
                    component = result.scalar_one_or_none()
                    if component is None:
                        component = Component(project_id=issue.project_id, name=comp_name)
                        db.add(component)
                        await db.flush()
                    db.add(IssueComponent(issue_id=issue.id, component_id=component.id))
            elif "remove" in op:
                comp_name = op["remove"].get("name") if isinstance(op["remove"], dict) else op["remove"]
                if comp_name:
                    for ca in list(issue.component_associations):
                        if ca.component.name == comp_name:
                            await db.delete(ca)

    # fixVersions
    if "fixVersions" in update_ops:
        for op in update_ops["fixVersions"]:
            if "add" in op:
                fv_name = op["add"].get("name") if isinstance(op["add"], dict) else op["add"]
                if fv_name:
                    result = await db.execute(
                        select(Version).where(
                            Version.project_id == issue.project_id,
                            Version.name == fv_name,
                        )
                    )
                    version = result.scalar_one_or_none()
                    if version is None:
                        version = Version(project_id=issue.project_id, name=fv_name)
                        db.add(version)
                        await db.flush()
                    db.add(IssueFixVersion(issue_id=issue.id, version_id=version.id))
            elif "remove" in op:
                fv_name = op["remove"].get("name") if isinstance(op["remove"], dict) else op["remove"]
                if fv_name:
                    for fva in list(issue.fix_version_associations):
                        if fva.version.name == fv_name:
                            await db.delete(fva)
            elif "set" in op:
                for fva in list(issue.fix_version_associations):
                    await db.delete(fva)
                await db.flush()
                set_versions = op["set"]
                for fv_data in set_versions:
                    fv_name = fv_data.get("name") if isinstance(fv_data, dict) else fv_data
                    if not fv_name:
                        continue
                    result = await db.execute(
                        select(Version).where(
                            Version.project_id == issue.project_id,
                            Version.name == fv_name,
                        )
                    )
                    version = result.scalar_one_or_none()
                    if version is None:
                        version = Version(project_id=issue.project_id, name=fv_name)
                        db.add(version)
                        await db.flush()
                    db.add(IssueFixVersion(issue_id=issue.id, version_id=version.id))

    # comment (add only)
    if "comment" in update_ops:
        for op in update_ops["comment"]:
            if "add" in op:
                comment_data = op["add"]
                body = comment_data.get("body", "") if isinstance(comment_data, dict) else str(comment_data)
                db.add(Comment(issue_id=issue.id, body=body))


# ---------------------------------------------------------------------------
# delete_issue
# ---------------------------------------------------------------------------

async def delete_issue(db: AsyncSession, issue_id_or_key: str) -> bool:
    """Delete an issue.  Returns ``True`` if deleted, ``False`` if not found."""
    issue = await get_issue(db, issue_id_or_key)
    if issue is None:
        return False
    await db.delete(issue)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# format_issue_response
# ---------------------------------------------------------------------------

async def format_issue_response(
    issue: Issue,
    base_url: str,
    db: AsyncSession,
    fields_filter: list[str] | None = None,
) -> dict:
    """Build the full Jira REST-style JSON response for a single issue.

    If *fields_filter* is provided and is not ``["*all"]``, only the
    listed field names are included in the ``fields`` dict.
    """

    # -- project ref --
    project_ref = {
        "self": f"{base_url}/rest/api/2/project/{issue.project.id}",
        "id": str(issue.project.id),
        "key": issue.project.key,
        "name": issue.project.name,
        "projectTypeKey": issue.project.project_type_key,
    }

    # -- issue type ref --
    issue_type_ref = {
        "self": f"{base_url}/rest/api/2/issuetype/{issue.issue_type.id}",
        "id": str(issue.issue_type.id),
        "description": issue.issue_type.description or "",
        "iconUrl": issue.issue_type.icon_url or "",
        "name": issue.issue_type.name,
        "subtask": issue.issue_type.subtask,
    }

    # -- status ref --
    status_ref = {
        "self": f"{base_url}/rest/api/2/status/{issue.status.id}",
        "description": issue.status.description or "",
        "iconUrl": "",
        "name": issue.status.name,
        "id": str(issue.status.id),
        "statusCategory": _status_category_for(issue.status.category),
    }

    # -- priority ref --
    priority_ref = None
    if issue.priority:
        priority_ref = {
            "self": f"{base_url}/rest/api/2/priority/{issue.priority.id}",
            "iconUrl": issue.priority.icon_url or "",
            "name": issue.priority.name,
            "id": str(issue.priority.id),
        }

    # -- resolution ref --
    resolution_ref = None
    if issue.resolution:
        resolution_ref = {
            "self": f"{base_url}/rest/api/2/resolution/{issue.resolution.id}",
            "id": str(issue.resolution.id),
            "description": issue.resolution.description or "",
            "name": issue.resolution.name,
        }

    # -- labels --
    labels = [lbl.label for lbl in issue.labels]

    # -- components --
    components = [
        {
            "self": f"{base_url}/rest/api/2/component/{ca.component.id}",
            "id": str(ca.component.id),
            "name": ca.component.name,
            "description": ca.component.description or "",
        }
        for ca in issue.component_associations
    ]

    # -- fix versions --
    fix_versions = [
        {
            "self": f"{base_url}/rest/api/2/version/{fva.version.id}",
            "id": str(fva.version.id),
            "name": fva.version.name,
            "description": fva.version.description or "",
            "released": fva.version.released,
            "releaseDate": str(fva.version.release_date) if fva.version.release_date else None,
        }
        for fva in issue.fix_version_associations
    ]

    # -- affects versions --
    affects_versions = [
        {
            "self": f"{base_url}/rest/api/2/version/{ava.version.id}",
            "id": str(ava.version.id),
            "name": ava.version.name,
            "description": ava.version.description or "",
            "released": ava.version.released,
            "releaseDate": str(ava.version.release_date) if ava.version.release_date else None,
        }
        for ava in issue.affects_version_associations
    ]

    # -- comments --
    comment_list = []
    for c in issue.comments:
        comment_list.append({
            "self": f"{base_url}/rest/api/2/issue/{issue.id}/comment/{c.id}",
            "id": str(c.id),
            "author": _format_user(c.author, base_url),
            "body": c.body,
            "updateAuthor": _format_user(c.author, base_url),
            "created": _format_datetime(c.created_at),
            "updated": _format_datetime(c.updated_at),
            "visibility": (
                {"type": c.visibility_type, "value": c.visibility_value}
                if c.visibility_type
                else None
            ),
        })

    comment_section = {
        "comments": comment_list,
        "maxResults": len(comment_list),
        "total": len(comment_list),
        "startAt": 0,
    }

    # -- issue links --
    issuelinks: list[dict] = []
    # outward_links: links where this issue is the outward side.
    # Show the OTHER issue (inward_issue) as outwardIssue in the response,
    # matching Jira's convention where the linked issue shown is always the
    # other end, not the current issue.
    for ol in issue.outward_links:
        issuelinks.append({
            "id": str(ol.id),
            "self": f"{base_url}/rest/api/2/issueLink/{ol.id}",
            "type": {
                "id": str(ol.link_type.id),
                "name": ol.link_type.name,
                "inward": ol.link_type.inward_description or "",
                "outward": ol.link_type.outward_description or "",
                "self": f"{base_url}/rest/api/2/issueLinkType/{ol.link_type.id}",
            },
            "outwardIssue": {
                "id": str(ol.inward_issue.id),
                "key": ol.inward_issue.key,
                "self": f"{base_url}/rest/api/2/issue/{ol.inward_issue.id}",
                "fields": {
                    "summary": ol.inward_issue.summary,
                },
            },
        })
    # inward_links: links where this issue is the inward side.
    # Show the OTHER issue (outward_issue) as inwardIssue in the response.
    for il in issue.inward_links:
        issuelinks.append({
            "id": str(il.id),
            "self": f"{base_url}/rest/api/2/issueLink/{il.id}",
            "type": {
                "id": str(il.link_type.id),
                "name": il.link_type.name,
                "inward": il.link_type.inward_description or "",
                "outward": il.link_type.outward_description or "",
                "self": f"{base_url}/rest/api/2/issueLinkType/{il.link_type.id}",
            },
            "inwardIssue": {
                "id": str(il.outward_issue.id),
                "key": il.outward_issue.key,
                "self": f"{base_url}/rest/api/2/issue/{il.outward_issue.id}",
                "fields": {
                    "summary": il.outward_issue.summary,
                },
            },
        })

    # -- parent --
    parent_ref = None
    if issue.parent:
        parent_ref = {
            "id": str(issue.parent.id),
            "key": issue.parent.key,
            "self": f"{base_url}/rest/api/2/issue/{issue.parent.id}",
            "fields": {
                "summary": issue.parent.summary,
                "issuetype": {
                    "self": f"{base_url}/rest/api/2/issuetype/{issue.parent.issue_type_id}",
                    "id": str(issue.parent.issue_type_id),
                    "name": "",
                    "subtask": False,
                },
            },
        }

    # -- watchers --
    watcher_count = len(issue.watchers)

    # -- custom fields: gather all registered custom fields --
    result = await db.execute(select(CustomField).order_by(CustomField.field_id))
    all_custom_fields = list(result.scalars().all())

    # Build a map of custom_field_id -> IssueCustomFieldValue for this issue
    cf_value_map: dict[int, IssueCustomFieldValue] = {
        cfv.custom_field_id: cfv for cfv in issue.custom_field_values
    }

    custom_fields_dict: dict[str, object] = {}
    for cf in all_custom_fields:
        cfv = cf_value_map.get(cf.id)
        if cfv is None:
            custom_fields_dict[cf.field_id] = None
        elif cf.field_type == "number":
            custom_fields_dict[cf.field_id] = cfv.value_number
        elif cf.field_type in ("select", "multiselect") and cfv.value_json:
            import json
            try:
                custom_fields_dict[cf.field_id] = json.loads(cfv.value_json)
            except (json.JSONDecodeError, TypeError):
                custom_fields_dict[cf.field_id] = cfv.value_string
        else:
            custom_fields_dict[cf.field_id] = cfv.value_string

    # -- due date --
    due_date_str = str(issue.due_date) if issue.due_date else None

    # -- build full fields dict --
    all_fields: dict[str, object] = {
        "issuetype": issue_type_ref,
        "project": project_ref,
        "summary": issue.summary,
        "description": issue.description,
        "status": status_ref,
        "priority": priority_ref,
        "resolution": resolution_ref,
        "assignee": _format_user(issue.assignee, base_url),
        "reporter": _format_user(issue.reporter, base_url),
        "creator": _format_user(issue.reporter, base_url),
        "labels": labels,
        "components": components,
        "fixVersions": fix_versions,
        "versions": affects_versions,
        "comment": comment_section,
        "issuelinks": issuelinks,
        "parent": parent_ref,
        "duedate": due_date_str,
        "created": _format_datetime(issue.created_at),
        "updated": _format_datetime(issue.updated_at),
        "resolutiondate": _format_datetime(issue.resolved_at),
        "watches": {
            "self": f"{base_url}/rest/api/2/issue/{issue.key}/watchers",
            "watchCount": watcher_count,
            "isWatching": False,
        },
        "subtasks": [],
        "attachment": [],
        "worklog": {"startAt": 0, "maxResults": 20, "total": 0, "worklogs": []},
        "timetracking": {},
        "environment": None,
        "aggregatetimeoriginalestimate": None,
        "aggregatetimeestimate": None,
        "aggregatetimespent": None,
        "timeestimate": None,
        "timeoriginalestimate": None,
        "timespent": None,
        "votes": {
            "self": f"{base_url}/rest/api/2/issue/{issue.key}/votes",
            "votes": 0,
            "hasVoted": False,
        },
    }

    # Merge custom fields into the fields dict
    all_fields.update(custom_fields_dict)

    # -- apply fields filter --
    if fields_filter and fields_filter != ["*all"]:
        if fields_filter == ["*navigable"]:
            # Navigable fields are the standard display fields
            navigable = {
                "issuetype", "project", "summary", "description", "status",
                "priority", "resolution", "assignee", "reporter", "creator",
                "labels", "components", "fixVersions", "versions", "comment",
                "issuelinks", "parent", "duedate", "created", "updated",
                "resolutiondate", "watches", "subtasks",
            }
            filtered: dict[str, object] = {}
            for f in navigable:
                if f in all_fields:
                    filtered[f] = all_fields[f]
            all_fields = filtered
        else:
            filtered = {}
            for f in fields_filter:
                if f in all_fields:
                    filtered[f] = all_fields[f]
            all_fields = filtered

    return {
        "expand": "renderedFields,names,schema,operations,editmeta,changelog",
        "id": str(issue.id),
        "self": f"{base_url}/rest/api/2/issue/{issue.id}",
        "key": issue.key,
        "fields": all_fields,
    }
