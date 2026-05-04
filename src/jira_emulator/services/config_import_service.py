"""Import v1.0 project configuration files into the emulator database."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.models import (
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
    Workflow,
    WorkflowTransition,
)

logger = logging.getLogger(__name__)


@dataclass
class ConfigImportResult:
    statuses: int = 0
    issue_types: int = 0
    priorities: int = 0
    resolutions: int = 0
    link_types: int = 0
    custom_fields: int = 0
    workflows: int = 0
    projects: int = 0
    errors: list[str] = field(default_factory=list)


async def import_project_config(db: AsyncSession, config: dict) -> ConfigImportResult:
    """Import a v1.0 project configuration into the database.

    Upserts all entities so the operation is idempotent.
    """
    result = ConfigImportResult()

    status_map = await _import_statuses(db, config.get("statuses", []), result)
    issue_type_map = await _import_issue_types(db, config.get("issue_types", []), result)
    await _import_priorities(db, config.get("priorities", []), result)
    await _import_resolutions(db, config.get("resolutions", []), result)
    await _import_link_types(db, config.get("link_types", []), result)
    await _import_custom_fields(db, config.get("custom_fields", []), result)
    workflow_map = await _import_workflows(db, config.get("workflows", []), status_map, result)
    await _import_project(db, config.get("project", {}), issue_type_map, workflow_map, result)

    await db.commit()
    logger.info(
        "Config import complete: %d statuses, %d issue_types, %d priorities, "
        "%d resolutions, %d link_types, %d custom_fields, %d workflows, %d projects",
        result.statuses,
        result.issue_types,
        result.priorities,
        result.resolutions,
        result.link_types,
        result.custom_fields,
        result.workflows,
        result.projects,
    )
    return result


async def _upsert_by_name(db: AsyncSession, model, name: str, defaults: dict):
    """Find or create a row by unique name. Returns the model instance."""
    stmt = select(model).where(model.name == name)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = model(name=name, **defaults)
        db.add(row)
    else:
        for k, v in defaults.items():
            setattr(row, k, v)
    return row


async def _import_statuses(db: AsyncSession, statuses: list[dict], result: ConfigImportResult) -> dict[str, Status]:
    status_map: dict[str, Status] = {}
    for s in statuses:
        try:
            row = await _upsert_by_name(
                db,
                Status,
                s["name"],
                {
                    "category": s.get("status_category", "indeterminate"),
                    "description": s.get("description"),
                },
            )
            status_map[s.get("status_id", s["name"])] = row
            result.statuses += 1
        except Exception as exc:
            result.errors.append(f"Status {s.get('name')}: {exc}")
    await db.flush()
    return status_map


async def _import_issue_types(
    db: AsyncSession, issue_types: list[dict], result: ConfigImportResult
) -> dict[str, IssueType]:
    it_map: dict[str, IssueType] = {}
    for it in issue_types:
        try:
            row = await _upsert_by_name(
                db,
                IssueType,
                it["name"],
                {
                    "subtask": it.get("subtask", False),
                    "description": it.get("description"),
                },
            )
            it_map[it["name"]] = row
            result.issue_types += 1
        except Exception as exc:
            result.errors.append(f"IssueType {it.get('name')}: {exc}")
    await db.flush()
    return it_map


async def _import_priorities(db: AsyncSession, priorities: list[dict], result: ConfigImportResult) -> None:
    for p in priorities:
        try:
            await _upsert_by_name(
                db,
                Priority,
                p["name"],
                {
                    "sort_order": p.get("sort_order", 0),
                },
            )
            result.priorities += 1
        except Exception as exc:
            result.errors.append(f"Priority {p.get('name')}: {exc}")
    await db.flush()


async def _import_resolutions(db: AsyncSession, resolutions: list[dict], result: ConfigImportResult) -> None:
    for r in resolutions:
        try:
            await _upsert_by_name(db, Resolution, r["name"], {})
            result.resolutions += 1
        except Exception as exc:
            result.errors.append(f"Resolution {r.get('name')}: {exc}")
    await db.flush()


async def _import_link_types(db: AsyncSession, link_types: list[dict], result: ConfigImportResult) -> None:
    for lt in link_types:
        try:
            await _upsert_by_name(
                db,
                IssueLinkType,
                lt["name"],
                {
                    "inward_description": lt.get("inward_description", ""),
                    "outward_description": lt.get("outward_description", ""),
                },
            )
            result.link_types += 1
        except Exception as exc:
            result.errors.append(f"LinkType {lt.get('name')}: {exc}")
    await db.flush()


async def _import_custom_fields(db: AsyncSession, custom_fields: list[dict], result: ConfigImportResult) -> None:
    for cf in custom_fields:
        try:
            field_id = cf["field_id"]
            stmt = select(CustomField).where(CustomField.field_id == field_id)
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = CustomField(
                    field_id=field_id,
                    name=cf["name"],
                    field_type=cf.get("field_type", "string"),
                    description=cf.get("description"),
                )
                db.add(row)
            else:
                row.name = cf["name"]
                row.field_type = cf.get("field_type", "string")
                if cf.get("description"):
                    row.description = cf["description"]
            result.custom_fields += 1
        except Exception as exc:
            result.errors.append(f"CustomField {cf.get('field_id')}: {exc}")
    await db.flush()


async def _import_workflows(
    db: AsyncSession,
    workflows: list[dict],
    status_map: dict[str, Status],
    result: ConfigImportResult,
) -> dict[str, Workflow]:
    wf_map: dict[str, Workflow] = {}
    for wf_data in workflows:
        try:
            wf_id = wf_data.get("workflow_id", wf_data["name"])
            wf_name = wf_data["name"]

            stmt = select(Workflow).where(Workflow.name == wf_name)
            wf = (await db.execute(stmt)).scalar_one_or_none()
            if wf is None:
                wf = Workflow(name=wf_name)
                db.add(wf)
                await db.flush()
            else:
                await db.execute(delete(WorkflowTransition).where(WorkflowTransition.workflow_id == wf.id))
                await db.flush()

            wf_statuses = wf_data.get("statuses", [])
            ordered = sorted(wf_statuses, key=lambda s: s.get("sequence", 0))

            for i, s_data in enumerate(ordered):
                sid = s_data["status_id"]
                status = status_map.get(sid)
                if status is None:
                    result.errors.append(f"Workflow {wf_name}: status_id {sid} not found in imported statuses")
                    continue

                if i == 0:
                    continue

                prev_sid = ordered[i - 1]["status_id"]
                prev_status = status_map.get(prev_sid)
                if prev_status is None:
                    continue

                db.add(
                    WorkflowTransition(
                        workflow_id=wf.id,
                        name=f"Move to {status.name}",
                        from_status_id=prev_status.id,
                        to_status_id=status.id,
                    )
                )

            # Global close transition if last status is "done" category
            if ordered:
                last_status = status_map.get(ordered[-1]["status_id"])
                if last_status and last_status.category == "done":
                    db.add(
                        WorkflowTransition(
                            workflow_id=wf.id,
                            name="Close",
                            from_status_id=None,
                            to_status_id=last_status.id,
                        )
                    )

            wf_map[wf_id] = wf
            result.workflows += 1
        except Exception as exc:
            result.errors.append(f"Workflow {wf_data.get('name')}: {exc}")

    await db.flush()
    return wf_map


async def _import_project(
    db: AsyncSession,
    project_data: dict,
    issue_type_map: dict[str, IssueType],
    workflow_map: dict[str, Workflow],
    result: ConfigImportResult,
) -> None:
    if not project_data or "key" not in project_data:
        return

    proj_key = project_data["key"]
    try:
        stmt = select(Project).where(Project.key == proj_key)
        proj = (await db.execute(stmt)).scalar_one_or_none()
        if proj is None:
            proj = Project(
                key=proj_key,
                name=project_data.get("name", proj_key),
                description=project_data.get("description"),
            )
            db.add(proj)
            await db.flush()
        else:
            proj.name = project_data.get("name", proj.name)
            if project_data.get("description"):
                proj.description = project_data["description"]
            await db.flush()

        # ProjectIssueType associations
        for it_name in project_data.get("issue_types", []):
            it = issue_type_map.get(it_name)
            if it is None:
                it_stmt = select(IssueType).where(IssueType.name == it_name)
                it = (await db.execute(it_stmt)).scalar_one_or_none()
            if it is None:
                result.errors.append(f"Project {proj_key}: issue type '{it_name}' not found")
                continue

            pit_stmt = select(ProjectIssueType).where(
                ProjectIssueType.project_id == proj.id,
                ProjectIssueType.issue_type_id == it.id,
            )
            if (await db.execute(pit_stmt)).scalar_one_or_none() is None:
                db.add(ProjectIssueType(project_id=proj.id, issue_type_id=it.id))
        await db.flush()

        # ProjectWorkflow associations
        for wf_mapping in project_data.get("workflows", []):
            wf_id = wf_mapping.get("workflow_id")
            it_name = wf_mapping.get("issue_type")
            wf = workflow_map.get(wf_id)
            if wf is None:
                continue
            it = issue_type_map.get(it_name)
            if it is None:
                it_stmt2 = select(IssueType).where(IssueType.name == it_name)
                it = (await db.execute(it_stmt2)).scalar_one_or_none()
            if it is None:
                continue

            pw_stmt = select(ProjectWorkflow).where(
                ProjectWorkflow.project_id == proj.id,
                ProjectWorkflow.issue_type_id == it.id,
            )
            existing = (await db.execute(pw_stmt)).scalar_one_or_none()
            if existing is None:
                db.add(ProjectWorkflow(project_id=proj.id, issue_type_id=it.id, workflow_id=wf.id))
            else:
                existing.workflow_id = wf.id
        await db.flush()

        # IssueSequence
        seq_stmt = select(IssueSequence).where(IssueSequence.project_id == proj.id)
        if (await db.execute(seq_stmt)).scalar_one_or_none() is None:
            db.add(IssueSequence(project_id=proj.id, next_number=1))
            await db.flush()

        result.projects += 1
    except Exception as exc:
        result.errors.append(f"Project {proj_key}: {exc}")
