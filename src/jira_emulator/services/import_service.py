"""Import service: bulk-import issues from JSON exports into the database."""

import json
import logging
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.adf import serialize_adf
from jira_emulator.models.comment import Comment
from jira_emulator.models.component import Component, IssueComponent
from jira_emulator.models.custom_field import CustomField, IssueCustomFieldValue
from jira_emulator.models.issue import Issue, IssueSequence
from jira_emulator.models.issue_property import IssueProperty
from jira_emulator.models.issue_type import IssueType
from jira_emulator.models.label import Label
from jira_emulator.models.link import IssueLink, IssueLinkType
from jira_emulator.models.priority import Priority
from jira_emulator.models.project import Project
from jira_emulator.models.resolution import Resolution
from jira_emulator.models.sprint import IssueSprint, Sprint
from jira_emulator.models.status import Status
from jira_emulator.models.user import User
from jira_emulator.models.version import IssueAffectsVersion, IssueFixVersion, Version
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
class ExportData:
    """Normalized container for data extracted from a Jira export file."""

    issues: list[dict] = field(default_factory=list)
    fields: list[dict] = field(default_factory=list)

    def merge(self, other: "ExportData") -> None:
        self.issues.extend(other.issues)
        self.fields.extend(other.fields)


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
        return datetime.fromisoformat(s.replace("+0000", "+00:00").replace("Z", "+00:00")).replace(tzinfo=None)
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


async def _get_or_create_user_from_display(db: AsyncSession, display_name: str, result: ImportResult) -> User:
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


async def _get_or_create_component(db: AsyncSession, project_id: int, name: str) -> Component:
    stmt = select(Component).where(Component.project_id == project_id, Component.name == name)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    c = Component(project_id=project_id, name=name)
    db.add(c)
    await db.flush()
    return c


async def _get_or_create_version(db: AsyncSession, project_id: int, name: str) -> Version:
    stmt = select(Version).where(Version.project_id == project_id, Version.name == name)
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


async def _get_or_create_custom_field(db: AsyncSession, field_id: str, name: str, field_type: str) -> CustomField:
    stmt = select(CustomField).where(CustomField.field_id == field_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    cf = CustomField(field_id=field_id, name=name, field_type=field_type)
    db.add(cf)
    await db.flush()
    return cf


async def _get_or_create_link_type(
    db: AsyncSession, name: str, inward: str | None = None, outward: str | None = None
) -> IssueLinkType:
    stmt = select(IssueLinkType).where(IssueLinkType.name == name)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    lt = IssueLinkType(name=name, inward_description=inward, outward_description=outward)
    db.add(lt)
    await db.flush()
    return lt


# ---------------------------------------------------------------------------
# Jira REST API format normalization
# ---------------------------------------------------------------------------
def _extract_name(obj: dict | str | None) -> str | None:
    """Extract .name from a Jira REST API object, or return the string as-is."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    return obj.get("name")


def _extract_display_name(obj: dict | str | None) -> str | None:
    """Extract .displayName from a Jira REST API user object."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    return obj.get("displayName")


def _normalize_jira_api_issue(raw: dict) -> dict:
    """Convert a Jira REST API issue dict to the flat import format.

    If the issue already uses the flat format (no ``fields`` dict), it is
    returned unchanged.
    """
    fields = raw.get("fields")
    if not isinstance(fields, dict):
        return raw

    flat: dict = {"key": raw.get("key", "")}

    flat["summary"] = fields.get("summary", "")
    flat["description"] = serialize_adf(fields.get("description"))

    flat["issue_type"] = _extract_name(fields.get("issuetype")) or "Task"
    flat["status"] = _extract_name(fields.get("status")) or "New"
    flat["priority"] = _extract_name(fields.get("priority"))
    flat["assignee"] = _extract_display_name(fields.get("assignee"))
    flat["reporter"] = _extract_display_name(fields.get("reporter"))

    resolution = fields.get("resolution")
    if isinstance(resolution, dict):
        flat["resolution"] = resolution.get("name")
    elif isinstance(resolution, str):
        flat["resolution"] = resolution

    flat["project"] = fields.get("project")
    flat["labels"] = fields.get("labels") or []
    flat["components"] = fields.get("components") or []
    flat["fix_versions"] = fields.get("fixVersions") or []
    flat["affects_versions"] = fields.get("versions") or []

    flat["created"] = fields.get("created")
    flat["updated"] = fields.get("updated")
    flat["due_date"] = fields.get("duedate")

    parent = fields.get("parent")
    if isinstance(parent, dict) and parent.get("key"):
        flat["epic_link"] = parent["key"]

    # Stash comments and links for post-processing
    comment_obj = fields.get("comment")
    if isinstance(comment_obj, dict):
        comments = comment_obj.get("comments")
        if comments:
            flat["_comments"] = comments
    elif isinstance(comment_obj, list):
        if comment_obj:
            flat["_comments"] = comment_obj

    issuelinks = fields.get("issuelinks")
    if issuelinks:
        flat["_issuelinks"] = issuelinks

    # Pass through custom fields
    for key, value in fields.items():
        if key.startswith("customfield_") and value is not None:
            flat[key] = value

    # Preserve top-level properties (sibling to fields in raw API response)
    if props := raw.get("properties"):
        flat["properties"] = props

    return flat


def _unwrap_export_envelope(data: dict | list) -> ExportData:
    """Unwrap a Jira export envelope into an ``ExportData`` container.

    Handles:
    - ``{"issues": [...], "fields": [...]}`` (full export)
    - ``{"metadata": {...}, "issues": [...]}`` (export script output)
    - ``{"issues": [...]}`` (bare issues wrapper)
    - ``[...]`` (plain list of issues)
    - ``{...}`` (single issue dict without "issues" key)
    """
    if isinstance(data, list):
        return ExportData(issues=data)
    if isinstance(data, dict):
        issues = data.get("issues")
        if isinstance(issues, list):
            fields = data.get("fields") or []
            return ExportData(issues=issues, fields=fields)
        return ExportData(issues=[data])
    return ExportData()


# ---------------------------------------------------------------------------
# Jira schema type -> emulator field type
# ---------------------------------------------------------------------------
_JIRA_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "number": "number",
    "date": "date",
    "datetime": "datetime",
    "option": "select",
    "array": "multiselect",
    "user": "user",
    "any": "string",
}


async def _import_field_metadata(db: AsyncSession, field_defs: list[dict]) -> int:
    """Import field definitions, creating or updating CustomField records.

    Only custom fields (``custom == True``) are processed.  Returns the
    number of fields created or updated.
    """
    count = 0
    for field_def in field_defs:
        if not field_def.get("custom"):
            continue

        field_id = field_def.get("id", "")
        if not field_id:
            continue

        name = field_def.get("name") or field_id
        description = field_def.get("description")
        schema = field_def.get("schema") or {}
        jira_type = schema.get("type", "string")
        field_type = _JIRA_TYPE_MAP.get(jira_type, "string")

        stmt = select(CustomField).where(CustomField.field_id == field_id)
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.name = name
            existing.field_type = field_type
            if description is not None:
                existing.description = description
        else:
            db.add(
                CustomField(
                    field_id=field_id,
                    name=name,
                    field_type=field_type,
                    description=description,
                )
            )
        count += 1

    await db.flush()
    return count


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
            existing_issue.description = serialize_adf(issue_data.get("description"))
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
                description=serialize_adf(issue_data.get("description")),
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
        existing_ic_stmt = select(IssueComponent).where(IssueComponent.issue_id == issue.id)
        for ic in (await db.execute(existing_ic_stmt)).scalars().all():
            await db.delete(ic)
        await db.flush()

        seen_components: set[str] = set()
        for comp_entry in issue_data.get("components") or []:
            comp_name = comp_entry.get("name") if isinstance(comp_entry, dict) else comp_entry
            if not comp_name or comp_name in seen_components:
                continue
            seen_components.add(comp_name)
            comp = await _get_or_create_component(db, project.id, comp_name)
            db.add(IssueComponent(issue_id=issue.id, component_id=comp.id))
        await db.flush()

        # ------------------------------------------------------------------
        # 12. Fix versions
        # ------------------------------------------------------------------
        existing_fv_stmt = select(IssueFixVersion).where(IssueFixVersion.issue_id == issue.id)
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
        existing_av_stmt = select(IssueAffectsVersion).where(IssueAffectsVersion.issue_id == issue.id)
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
        existing_cf_stmt = select(IssueCustomFieldValue).where(IssueCustomFieldValue.issue_id == issue.id)
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
            cf = await _get_or_create_custom_field(db, cf_field_id, cf_name, cf_type_map.get(value_type, "string"))

            cfv = IssueCustomFieldValue(issue_id=issue.id, custom_field_id=cf.id)
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

        # Also process raw customfield_* keys directly from the payload
        for raw_key, raw_value in issue_data.items():
            if not raw_key.startswith("customfield_") or raw_value is None:
                continue
            # Skip if already handled by CUSTOM_FIELD_MAP
            mapped_ids = {v[0] for v in CUSTOM_FIELD_MAP.values()}
            if raw_key in mapped_ids:
                continue

            if isinstance(raw_value, (dict, list)):
                inferred_type = "multiselect"
            elif isinstance(raw_value, (int, float)):
                inferred_type = "number"
            else:
                inferred_type = "string"

            cf = await _get_or_create_custom_field(db, raw_key, raw_key, inferred_type)
            cfv = IssueCustomFieldValue(issue_id=issue.id, custom_field_id=cf.id)
            # Use the field's stored type (which may have been set by field
            # metadata import) to decide the storage column, so that the
            # response serializer reads from the correct column.
            store_type = cf.field_type
            if store_type == "number":
                try:
                    cfv.value_number = float(raw_value)
                except (TypeError, ValueError):
                    cfv.value_string = str(raw_value)
            elif store_type in ("select", "multiselect"):
                if isinstance(raw_value, (dict, list)):
                    cfv.value_json = json.dumps(raw_value)
                else:
                    cfv.value_string = str(raw_value)
            else:
                if isinstance(raw_value, (dict, list)):
                    cfv.value_string = json.dumps(raw_value)
                else:
                    cfv.value_string = str(raw_value)
            db.add(cfv)

        await db.flush()

        # ------------------------------------------------------------------
        # 15. Sprints
        # ------------------------------------------------------------------
        existing_is_stmt = select(IssueSprint).where(IssueSprint.issue_id == issue.id)
        for isp in (await db.execute(existing_is_stmt)).scalars().all():
            await db.delete(isp)
        await db.flush()

        for sprint_name in issue_data.get("sprints") or []:
            sprint = await _get_or_create_sprint(db, sprint_name)
            db.add(IssueSprint(issue_id=issue.id, sprint_id=sprint.id))
        await db.flush()

        # ------------------------------------------------------------------
        # 16. Comments (from Jira REST API format)
        # ------------------------------------------------------------------
        for comment_data in issue_data.get("_comments") or []:
            body = serialize_adf(comment_data.get("body"))
            if not body:
                continue
            author_obj = comment_data.get("author")
            author = None
            if author_obj:
                display = _extract_display_name(author_obj)
                if display:
                    author = await _get_or_create_user_from_display(db, display, result)
            comment_created = _parse_datetime(comment_data.get("created")) or datetime.utcnow()
            comment_updated = _parse_datetime(comment_data.get("updated")) or comment_created
            db.add(
                Comment(
                    issue_id=issue.id,
                    author_id=author.id if author else None,
                    body=body,
                    created_at=comment_created,
                    updated_at=comment_updated,
                )
            )
        await db.flush()

        # ------------------------------------------------------------------
        # 17. Properties
        # ------------------------------------------------------------------
        existing_props_stmt = select(IssueProperty).where(IssueProperty.issue_id == issue.id)
        for prop in (await db.execute(existing_props_stmt)).scalars().all():
            await db.delete(prop)
        await db.flush()

        for prop_key, prop_value in (issue_data.get("properties") or {}).items():
            db.add(IssueProperty(issue_id=issue.id, key=prop_key, value=json.dumps(prop_value)))
        await db.flush()

        # ------------------------------------------------------------------
        # 18. Epic link — defer to second pass
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
async def _resolve_epic_links(db: AsyncSession, epic_links: dict[str, str]) -> list[str]:
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
                logger.debug("Skipping parent link %s -> %s (parent not in database)", issue_key, epic_key)
                continue

            child.parent_id = parent.id
        except Exception as exc:
            errors.append(f"{issue_key}: epic link error: {exc}")

    await db.flush()
    return errors


async def _resolve_issue_links(db: AsyncSession, deferred_links: list[dict]) -> list[str]:
    """Resolve deferred issue links after all issues have been imported.

    Each entry has ``_source_key`` (the issue that had the link) plus either
    ``inwardIssue`` or ``outwardIssue`` (Jira REST API link format).
    """
    errors: list[str] = []
    for link_data in deferred_links:
        try:
            source_key = link_data.get("_source_key", "")
            link_type_info = link_data.get("type", {})
            link_type_name = link_type_info.get("name", "Related")

            inward_issue_info = link_data.get("inwardIssue")
            outward_issue_info = link_data.get("outwardIssue")

            if inward_issue_info:
                target_key = inward_issue_info.get("key", "")
                # The imported link is from the source issue's GET perspective:
                # source shows target under inwardIssue. Internally, that means
                # source is the stored outward endpoint and target is stored
                # inward, so the serializer can reproduce the same GET shape.
                inward_key = target_key
                outward_key = source_key
            elif outward_issue_info:
                target_key = outward_issue_info.get("key", "")
                # Source shows target under outwardIssue. Internally, that
                # means source is the stored inward endpoint and target is
                # stored outward.
                inward_key = source_key
                outward_key = target_key
            else:
                continue

            if not target_key:
                continue

            inward_stmt = select(Issue).where(Issue.key == inward_key)
            inward_issue = (await db.execute(inward_stmt)).scalar_one_or_none()
            outward_stmt = select(Issue).where(Issue.key == outward_key)
            outward_issue = (await db.execute(outward_stmt)).scalar_one_or_none()

            if not inward_issue or not outward_issue:
                continue

            link_type = await _get_or_create_link_type(
                db,
                link_type_name,
                inward=link_type_info.get("inward"),
                outward=link_type_info.get("outward"),
            )

            # Avoid duplicates
            existing = (
                await db.execute(
                    select(IssueLink).where(
                        IssueLink.link_type_id == link_type.id,
                        IssueLink.inward_issue_id == inward_issue.id,
                        IssueLink.outward_issue_id == outward_issue.id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            db.add(
                IssueLink(
                    link_type_id=link_type.id,
                    inward_issue_id=inward_issue.id,
                    outward_issue_id=outward_issue.id,
                )
            )
        except Exception as exc:
            errors.append(f"issue link: {exc}")

    await db.flush()
    return errors


# ---------------------------------------------------------------------------
# Batch import entry point
# ---------------------------------------------------------------------------
async def import_issues(db: AsyncSession, data: ExportData | list[dict]) -> ImportResult:
    """Import export data (field metadata + issues + link resolution).

    This is the main entry point for programmatic imports.  Accepts an
    ``ExportData`` container or a plain list of issue dicts for backwards
    compatibility.
    """
    if isinstance(data, list):
        data = ExportData(issues=data)

    result = ImportResult()
    epic_links: dict[str, str] = {}
    deferred_links: list[dict] = []

    # Phase 0: import field metadata (before issues so CustomField records
    # are pre-populated with correct names and types)
    if data.fields:
        field_count = await _import_field_metadata(db, data.fields)
        logger.info("Imported %d field definitions", field_count)

    # Normalize issues (handles Jira REST API format)
    normalized = [_normalize_jira_api_issue(issue) for issue in data.issues]

    # First pass: import every issue
    for issue_data in normalized:
        key = issue_data.get("key", "")
        if not key or "-" not in key:
            result.errors.append(f"Skipping issue with missing or invalid key: {key!r}")
            continue
        await import_issue(db, issue_data, result, epic_links=epic_links)
        # Collect deferred issue links
        for link in issue_data.get("_issuelinks") or []:
            link["_source_key"] = key
            deferred_links.append(link)

    # Second pass: resolve epic / parent links
    if epic_links:
        link_errors = await _resolve_epic_links(db, epic_links)
        result.errors.extend(link_errors)

    # Third pass: resolve issue links
    if deferred_links:
        link_errors = await _resolve_issue_links(db, deferred_links)
        result.errors.extend(link_errors)

    # Update issue sequences so that the next created issue gets a correct number
    project_keys: set[str] = set()
    for issue_data in normalized:
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

        max_stmt = select(func.max(Issue.key)).where(Issue.project_id == project.id)
        max_key = (await db.execute(max_stmt)).scalar_one_or_none()
        if max_key and "-" in max_key:
            max_number = int(max_key.rsplit("-", 1)[1])
        else:
            max_number = 0

        seq_stmt = select(IssueSequence).where(IssueSequence.project_id == project.id)
        seq = (await db.execute(seq_stmt)).scalar_one_or_none()
        if seq:
            seq.next_number = max_number + 1
        else:
            db.add(IssueSequence(project_id=project.id, next_number=max_number + 1))

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
    """Read a JSON file and import its contents.

    The file may be a JSON array of issue dicts, a single issue dict, or a
    Jira export envelope (``{"issues": [...], "fields": [...]}``)
    """
    file_path = Path(path)
    logger.info("Importing from file: %s", file_path)
    with open(file_path, encoding="utf-8") as fh:
        data = json.load(fh)

    export_data = _unwrap_export_envelope(data)
    if not export_data.issues and not isinstance(data, (list, dict)):
        result = ImportResult()
        result.errors.append(f"{path}: unexpected JSON root type {type(data).__name__}")
        return result
    return await import_issues(db, export_data)


async def import_directory(db: AsyncSession, dir_path: str) -> ImportResult:
    """Scan a directory for ``*.json`` files, combine all data, and import.

    All data from every file is collected into a single ``ExportData``
    before importing so that cross-file epic links can be resolved in one
    pass.
    """
    directory = Path(dir_path)
    logger.info("Scanning directory for JSON files: %s", directory)

    combined = ExportData()
    errors: list[str] = []

    for json_file in sorted(directory.glob("*.json")):
        try:
            with open(json_file, encoding="utf-8") as fh:
                data = json.load(fh)
            combined.merge(_unwrap_export_envelope(data))
        except Exception as exc:
            errors.append(f"{json_file}: {exc}")

    logger.info("Collected %d issues from %s", len(combined.issues), directory)

    result = await import_issues(db, combined)
    result.errors.extend(errors)
    return result


def _find_json_files_recursive(directory: Path) -> list[Path]:
    """Recursively find all .json files in a directory tree."""
    return sorted(directory.rglob("*.json"))


async def import_archive(db: AsyncSession, archive_path: str) -> ImportResult:
    """Extract a .tar.gz or .zip archive and import all JSON files found within.

    The archive is extracted to a temporary directory, all .json files are
    recursively collected, and then imported as a batch.
    """
    archive_file = Path(archive_path)
    logger.info("Importing from archive: %s", archive_file)

    combined = ExportData()
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Extract the archive
        try:
            if archive_file.suffix == ".zip":
                with zipfile.ZipFile(archive_file, "r") as zf:
                    zf.extractall(temp_path)
            elif archive_file.name.endswith(".tar.gz") or archive_file.suffix in {".tgz", ".tar"}:
                with tarfile.open(archive_file, "r:*") as tf:
                    tf.extractall(temp_path)
            else:
                result = ImportResult()
                result.errors.append(
                    f"{archive_path}: unsupported archive format (expected .zip, .tar.gz, .tgz, or .tar)"
                )
                return result
        except Exception as exc:
            result = ImportResult()
            result.errors.append(f"{archive_path}: failed to extract archive: {exc}")
            return result

        # Recursively find all JSON files
        json_files = _find_json_files_recursive(temp_path)
        logger.info("Found %d JSON files in archive", len(json_files))

        # Load and collect all data
        for json_file in json_files:
            try:
                with open(json_file, encoding="utf-8") as fh:
                    data = json.load(fh)
                combined.merge(_unwrap_export_envelope(data))
            except Exception as exc:
                errors.append(f"{json_file.name}: {exc}")

    logger.info("Collected %d issues from archive %s", len(combined.issues), archive_file)

    result = await import_issues(db, combined)
    result.errors.extend(errors)
    return result
