"""Import service: bulk-import issues from JSON exports into the database."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.models.issue import Issue, IssueSequence
from jira_emulator.models.project import Project
from jira_emulator.models.issue_type import IssueType
from jira_emulator.models.status import Status
from jira_emulator.models.priority import Priority
from jira_emulator.models.resolution import Resolution
from jira_emulator.models.user import User
from jira_emulator.models.label import Label
from jira_emulator.models.component import Component, IssueComponent
from jira_emulator.models.version import Version, IssueFixVersion, IssueAffectsVersion
from jira_emulator.models.custom_field import CustomField, IssueCustomFieldValue
from jira_emulator.models.sprint import Sprint, IssueSprint
from jira_emulator.services.user_service import get_or_create_user, slugify_username

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom field mapping: import-JSON key -> (custom field_id, value column)
# ---------------------------------------------------------------------------
CUSTOM_FIELD_MAP: dict[str, tuple[str, str]] = {
    "team": ("customfield_12313240", "string"),
    "story_points": ("customfield_12310243", "number"),
    "target_start": ("customfield_12313941", "string"),
    "target_end": ("customfield_12313942", "string"),
    "affects_testing": ("customfield_12310170", "json"),
    "release_blocker": ("customfield_12319743", "string"),
    "severity": ("customfield_12316142", "string"),
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class ImportResult:
    """Tracks statistics and errors produced by an import run."""

    imported: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)
    projects_created: list[str] = field(default_factory=list)
    users_created: list[str] = field(default_factory=list)

    def merge(self, other: "ImportResult") -> None:
        self.imported += other.imported
        self.updated += other.updated
        self.errors.extend(other.errors)
        self.projects_created.extend(other.projects_created)
        self.users_created.extend(other.users_created)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_datetime(s: str | None) -> datetime | None:
    """Parse an ISO-8601-ish timestamp into a naive UTC datetime."""
    if not s:
        return None
    try:
        return (
            datetime.fromisoformat(
                s.replace("+0000", "+00:00").replace("Z", "+00:00")
            )
            .replace(tzinfo=None)
        )
    except (ValueError, AttributeError):
        return None


def _parse_issue_key(key: str) -> tuple[str, int]:
    """Split 'PROJ-123' into ('PROJ', 123)."""
    parts = key.rsplit("-", 1)
    return parts[0], int(parts[1])


# ---------------------------------------------------------------------------
# Look-up-or-create helpers (thin wrappers around simple SELECT / INSERT)
# ---------------------------------------------------------------------------
async def _get_or_create_project(
    db: AsyncSession, project_key: str, project_name: str | None, result: ImportResult
) -> Project:
    stmt = select(Project).where(Project.key == project_key)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    project = Project(key=project_key, name=project_name or project_key)
    db.add(project)
    await db.flush()
    result.projects_created.append(project_key)
    return project


async def _get_or_create_issue_type(db: AsyncSession, name: str) -> IssueType:
    stmt = select(IssueType).where(IssueType.name == name)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    it = IssueType(name=name)
    db.add(it)
    await db.flush()
    return it


async def _get_or_create_status(db: AsyncSession, name: str) -> Status:
    stmt = select(Status).where(Status.name == name)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    s = Status(name=name, category="indeterminate")
    db.add(s)
    await db.flush()
    return s


async def _get_or_create_priority(db: AsyncSession, name: str) -> Priority:
    stmt = select(Priority).where(Priority.name == name)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    p = Priority(name=name)
    db.add(p)
    await db.flush()
    return p


async def _get_or_create_resolution(db: AsyncSession, name: str) -> Resolution:
    stmt = select(Resolution).where(Resolution.name == name)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    r = Resolution(name=name)
    db.add(r)
    await db.flush()
    return r


async def _get_or_create_user_from_display(
    db: AsyncSession, display_name: str, result: ImportResult
) -> User:
    """Resolve a display name to a User, creating one if necessary."""
    username = slugify_username(display_name)
    # Check if user already exists before calling get_or_create_user so we can
    # track whether a new record was actually created.
    stmt = select(User).where(User.username == username)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    user = await get_or_create_user(db, display_name=display_name, username=username)
    if existing is None:
        result.users_created.append(username)
    return user


async def _get_or_create_component(
    db: AsyncSession, project_id: int, name: str
) -> Component:
    stmt = select(Component).where(
        Component.project_id == project_id, Component.name == name
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    c = Component(project_id=project_id, name=name)
    db.add(c)
    await db.flush()
    return c


async def _get_or_create_version(
    db: AsyncSession, project_id: int, name: str
) -> Version:
    stmt = select(Version).where(
        Version.project_id == project_id, Version.name == name
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    v = Version(project_id=project_id, name=name)
    db.add(v)
    await db.flush()
    return v


async def _get_or_create_sprint(db: AsyncSession, name: str) -> Sprint:
    stmt = select(Sprint).where(Sprint.name == name)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    sp = Sprint(name=name)
    db.add(sp)
    await db.flush()
    return sp


async def _get_or_create_custom_field(
    db: AsyncSession, field_id: str, name: str, field_type: str
) -> CustomField:
    stmt = select(CustomField).where(CustomField.field_id == field_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    cf = CustomField(field_id=field_id, name=name, field_type=field_type)
    db.add(cf)
    await db.flush()
    return cf


# ---------------------------------------------------------------------------
# Single-issue import
# ---------------------------------------------------------------------------
async def import_issue(
    db: AsyncSession,
    issue_data: dict,
    result: ImportResult,
    epic_links: dict[str, str] | None = None,
) -> None:
    """Import (or update) a single issue from an export dict.

    *epic_links* is an accumulator dict mapping ``issue_key -> epic_key`` that
    will be resolved in a second pass so that forward-references work.
    """
    issue_key: str = issue_data.get("key", "")
    try:
        project_key, issue_number = _parse_issue_key(issue_key)

        # 1. Auto-create project
        proj_info = issue_data.get("project") or {}
        proj_name = proj_info.get("name") if isinstance(proj_info, dict) else None
        project = await _get_or_create_project(db, project_key, proj_name, result)

        # 2. Auto-create issue type
        issue_type_name = issue_data.get("issue_type") or "Task"
        issue_type = await _get_or_create_issue_type(db, issue_type_name)

        # 3. Auto-create status
        status_name = issue_data.get("status") or "New"
        status = await _get_or_create_status(db, status_name)

        # 4. Auto-create priority
        priority = None
        priority_name = issue_data.get("priority")
        if priority_name:
            priority = await _get_or_create_priority(db, priority_name)

        # 5. Auto-create users
        assignee = None
        assignee_name = issue_data.get("assignee")
        if assignee_name:
            assignee = await _get_or_create_user_from_display(db, assignee_name, result)

        reporter = None
        reporter_name = issue_data.get("reporter")
        if reporter_name:
            reporter = await _get_or_create_user_from_display(db, reporter_name, result)

        # 6. Resolution
        resolution = None
        resolution_val = issue_data.get("resolution")
        if isinstance(resolution_val, str):
            resolution = await _get_or_create_resolution(db, resolution_val)

        # 7. Timestamps
        created_at = _parse_datetime(issue_data.get("created")) or datetime.utcnow()
        updated_at = _parse_datetime(issue_data.get("updated")) or datetime.utcnow()

        # 8. Due date
        due_date_str = issue_data.get("due_date")
        due_date = None
        if due_date_str:
            try:
                due_date = datetime.fromisoformat(due_date_str).date()
            except (ValueError, AttributeError):
                pass

        # 9. Check idempotency — update or insert
        stmt = select(Issue).where(Issue.key == issue_key)
        existing_issue = (await db.execute(stmt)).scalar_one_or_none()

        if existing_issue:
            # UPDATE path
            existing_issue.summary = issue_data.get("summary", existing_issue.summary)
            existing_issue.description = issue_data.get("description")
            existing_issue.project_id = project.id
            existing_issue.issue_type_id = issue_type.id
            existing_issue.status_id = status.id
            existing_issue.priority_id = priority.id if priority else None
            existing_issue.assignee_id = assignee.id if assignee else None
            existing_issue.reporter_id = reporter.id if reporter else None
            existing_issue.resolution_id = resolution.id if resolution else None
            existing_issue.due_date = due_date
            existing_issue.created_at = created_at
            existing_issue.updated_at = updated_at
            issue = existing_issue
            result.updated += 1
        else:
            # INSERT path
            issue = Issue(
                key=issue_key,
                project_id=project.id,
                issue_type_id=issue_type.id,
                summary=issue_data.get("summary", ""),
                description=issue_data.get("description"),
                status_id=status.id,
                priority_id=priority.id if priority else None,
                assignee_id=assignee.id if assignee else None,
                reporter_id=reporter.id if reporter else None,
                resolution_id=resolution.id if resolution else None,
                due_date=due_date,
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(issue)
            result.imported += 1

        await db.flush()

        # ------------------------------------------------------------------
        # 10. Labels — replace existing set
        # ------------------------------------------------------------------
        # Delete old labels
        existing_labels_stmt = select(Label).where(Label.issue_id == issue.id)
        existing_labels = (await db.execute(existing_labels_stmt)).scalars().all()
        for lbl in existing_labels:
            await db.delete(lbl)
        await db.flush()

        for label_text in issue_data.get("labels") or []:
            db.add(Label(issue_id=issue.id, label=label_text))
        await db.flush()

        # ------------------------------------------------------------------
        # 11. Components
        # ------------------------------------------------------------------
        # Delete old associations
        existing_ic_stmt = select(IssueComponent).where(
            IssueComponent.issue_id == issue.id
        )
        for ic in (await db.execute(existing_ic_stmt)).scalars().all():
            await db.delete(ic)
        await db.flush()

        for comp_entry in issue_data.get("components") or []:
            comp_name = comp_entry.get("name") if isinstance(comp_entry, dict) else comp_entry
            if not comp_name:
                continue
            comp = await _get_or_create_component(db, project.id, comp_name)
            db.add(IssueComponent(issue_id=issue.id, component_id=comp.id))
        await db.flush()

        # ------------------------------------------------------------------
        # 12. Fix versions
        # ------------------------------------------------------------------
        existing_fv_stmt = select(IssueFixVersion).where(
            IssueFixVersion.issue_id == issue.id
        )
        for fv in (await db.execute(existing_fv_stmt)).scalars().all():
            await db.delete(fv)
        await db.flush()

        for ver_entry in issue_data.get("fix_versions") or []:
            ver_name = ver_entry.get("name") if isinstance(ver_entry, dict) else ver_entry
            if not ver_name:
                continue
            ver = await _get_or_create_version(db, project.id, ver_name)
            db.add(IssueFixVersion(issue_id=issue.id, version_id=ver.id))
        await db.flush()

        # ------------------------------------------------------------------
        # 13. Affects versions
        # ------------------------------------------------------------------
        existing_av_stmt = select(IssueAffectsVersion).where(
            IssueAffectsVersion.issue_id == issue.id
        )
        for av in (await db.execute(existing_av_stmt)).scalars().all():
            await db.delete(av)
        await db.flush()

        for ver_entry in issue_data.get("affects_versions") or []:
            ver_name = ver_entry.get("name") if isinstance(ver_entry, dict) else ver_entry
            if not ver_name:
                continue
            ver = await _get_or_create_version(db, project.id, ver_name)
            db.add(IssueAffectsVersion(issue_id=issue.id, version_id=ver.id))
        await db.flush()

        # ------------------------------------------------------------------
        # 14. Custom fields
        # ------------------------------------------------------------------
        # Remove old custom field values for this issue
        existing_cf_stmt = select(IssueCustomFieldValue).where(
            IssueCustomFieldValue.issue_id == issue.id
        )
        for cfv in (await db.execute(existing_cf_stmt)).scalars().all():
            await db.delete(cfv)
        await db.flush()

        for json_key, (cf_field_id, value_type) in CUSTOM_FIELD_MAP.items():
            raw_value = issue_data.get(json_key)
            if raw_value is None:
                continue

            # Derive a human-friendly name from the JSON key
            cf_name = json_key.replace("_", " ").title()
            cf_type_map = {
                "string": "string",
                "number": "number",
                "json": "multiselect",
            }
            cf = await _get_or_create_custom_field(
                db, cf_field_id, cf_name, cf_type_map.get(value_type, "string")
            )

            cfv = IssueCustomFieldValue(
                issue_id=issue.id, custom_field_id=cf.id
            )
            if value_type == "number":
                try:
                    cfv.value_number = float(raw_value)
                except (TypeError, ValueError):
                    cfv.value_string = str(raw_value)
            elif value_type == "json":
                cfv.value_json = json.dumps(raw_value)
            else:
                cfv.value_string = str(raw_value)

            db.add(cfv)
        await db.flush()

        # ------------------------------------------------------------------
        # 15. Sprints
        # ------------------------------------------------------------------
        existing_is_stmt = select(IssueSprint).where(
            IssueSprint.issue_id == issue.id
        )
        for isp in (await db.execute(existing_is_stmt)).scalars().all():
            await db.delete(isp)
        await db.flush()

        for sprint_name in issue_data.get("sprints") or []:
            sprint = await _get_or_create_sprint(db, sprint_name)
            db.add(IssueSprint(issue_id=issue.id, sprint_id=sprint.id))
        await db.flush()

        # ------------------------------------------------------------------
        # 16. Epic link — defer to second pass
        # ------------------------------------------------------------------
        epic_link_key = issue_data.get("epic_link")
        if epic_link_key and epic_links is not None:
            epic_links[issue_key] = epic_link_key

    except Exception as exc:
        result.errors.append(f"{issue_key}: {exc}")
        logger.exception("Error importing issue %s", issue_key)


# ---------------------------------------------------------------------------
# Epic-link resolution (second pass)
# ---------------------------------------------------------------------------
async def _resolve_epic_links(
    db: AsyncSession, epic_links: dict[str, str]
) -> list[str]:
    """Resolve deferred epic_link references by setting parent_id.

    Returns a list of error messages for links that could not be resolved.
    """
    errors: list[str] = []
    for issue_key, epic_key in epic_links.items():
        try:
            child_stmt = select(Issue).where(Issue.key == issue_key)
            child = (await db.execute(child_stmt)).scalar_one_or_none()
            if child is None:
                errors.append(f"{issue_key}: child issue not found for epic link")
                continue

            parent_stmt = select(Issue).where(Issue.key == epic_key)
            parent = (await db.execute(parent_stmt)).scalar_one_or_none()
            if parent is None:
                errors.append(
                    f"{issue_key}: epic {epic_key} not found, cannot set parent"
                )
                continue

            child.parent_id = parent.id
        except Exception as exc:
            errors.append(f"{issue_key}: epic link error: {exc}")

    await db.flush()
    return errors


# ---------------------------------------------------------------------------
# Batch import entry point
# ---------------------------------------------------------------------------
async def import_issues(db: AsyncSession, issues: list[dict]) -> ImportResult:
    """Import a list of issue dicts (first pass + epic resolution + sequences).

    This is the main entry point for programmatic imports.
    """
    result = ImportResult()
    epic_links: dict[str, str] = {}

    # First pass: import every issue
    for issue_data in issues:
        await import_issue(db, issue_data, result, epic_links=epic_links)

    # Second pass: resolve epic / parent links
    if epic_links:
        link_errors = await _resolve_epic_links(db, epic_links)
        result.errors.extend(link_errors)

    # Update issue sequences so that the next created issue gets a correct number
    project_keys: set[str] = set()
    for issue_data in issues:
        key = issue_data.get("key", "")
        if "-" in key:
            project_keys.add(key.rsplit("-", 1)[0])

    for pkey in project_keys:
        proj_stmt = select(Project).where(Project.key == pkey)
        project = (await db.execute(proj_stmt)).scalar_one_or_none()
        if project is None:
            continue

        # Find the maximum issue number for this project
        from sqlalchemy import func  # local import to keep top-level clean

        max_stmt = (
            select(func.max(Issue.key))
            .where(Issue.project_id == project.id)
        )
        max_key = (await db.execute(max_stmt)).scalar_one_or_none()
        if max_key and "-" in max_key:
            max_number = int(max_key.rsplit("-", 1)[1])
        else:
            max_number = 0

        seq_stmt = select(IssueSequence).where(
            IssueSequence.project_id == project.id
        )
        seq = (await db.execute(seq_stmt)).scalar_one_or_none()
        if seq:
            seq.next_number = max_number + 1
        else:
            db.add(
                IssueSequence(project_id=project.id, next_number=max_number + 1)
            )

    await db.flush()
    await db.commit()

    logger.info(
        "Import complete: %d imported, %d updated, %d errors",
        result.imported,
        result.updated,
        len(result.errors),
    )
    return result


# ---------------------------------------------------------------------------
# File / directory helpers
# ---------------------------------------------------------------------------
async def import_file(db: AsyncSession, path: str) -> ImportResult:
    """Read a JSON file and import the issues it contains.

    The file may be a JSON array of issue dicts **or** a single issue dict.
    """
    file_path = Path(path)
    logger.info("Importing from file: %s", file_path)
    with open(file_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, list):
        return await import_issues(db, data)
    elif isinstance(data, dict):
        return await import_issues(db, [data])
    else:
        result = ImportResult()
        result.errors.append(f"{path}: unexpected JSON root type {type(data).__name__}")
        return result


async def import_directory(db: AsyncSession, dir_path: str) -> ImportResult:
    """Scan a directory for ``*.json`` files, combine all issues, and import.

    All issue dicts from every file are collected into a single list before
    importing so that cross-file epic links can be resolved in one pass.
    """
    directory = Path(dir_path)
    logger.info("Scanning directory for JSON files: %s", directory)

    all_issues: list[dict] = []
    errors: list[str] = []

    for json_file in sorted(directory.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                all_issues.extend(data)
            elif isinstance(data, dict):
                all_issues.append(data)
            else:
                errors.append(
                    f"{json_file}: unexpected JSON root type {type(data).__name__}"
                )
        except Exception as exc:
            errors.append(f"{json_file}: {exc}")

    logger.info("Collected %d issues from %s", len(all_issues), directory)

    result = await import_issues(db, all_issues)
    result.errors.extend(errors)
    return result
