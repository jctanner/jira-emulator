"""Admin endpoints: /api/admin/import, /api/admin/reset, /api/admin/snapshots."""

import json
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.database import Base, get_db, get_engine, get_session_factory
from jira_emulator.models.user import User
from jira_emulator.schemas.admin import ImportRequest, ImportResponse
from jira_emulator.services.config_import_service import import_project_config
from jira_emulator.services.import_service import import_archive, import_issues
from jira_emulator.services.project_admin_service import create_project, delete_project
from jira_emulator.services.seed_service import load_seed_data
from jira_emulator.services.snapshot_service import (
    create_snapshot,
    delete_snapshot,
    is_snapshot_enabled,
    list_snapshots,
    restore_snapshot,
)

router = APIRouter(prefix="/api/admin")


class AdminProjectCreateBody(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    lead: str | None = None
    project_type_key: str = "software"


def _project_response(project) -> dict:
    return {
        "id": str(project.id),
        "key": project.key,
        "name": project.name,
        "description": project.description or "",
        "lead": project.lead or "",
        "projectTypeKey": project.project_type_key,
    }


@router.post("/import", response_model=ImportResponse)
async def import_data(
    body: ImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import issues into the Jira emulator."""
    result = await import_issues(db, body.issues)
    return ImportResponse(
        imported=result.imported,
        updated=result.updated,
        errors=result.errors,
        projects_created=result.projects_created,
        users_created=result.users_created,
    )


@router.post("/import/file", response_model=ImportResponse)
async def import_file_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import issues from a JSON or archive file upload (.json, .zip, .tar.gz, .tgz, .tar)."""
    filename = file.filename or ""

    # Check if this is an archive file
    is_archive = (
        filename.endswith(".tar.gz")
        or filename.endswith(".tgz")
        or filename.endswith(".tar")
        or filename.endswith(".zip")
    )

    if is_archive:
        # Save uploaded archive to a temporary file and process it
        # Determine the suffix (handle multi-part extensions like .tar.gz)
        if filename.endswith(".tar.gz"):
            suffix = ".tar.gz"
        else:
            suffix = os.path.splitext(filename)[1]

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        try:
            result = await import_archive(db, temp_path)
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    else:
        # Process as JSON file
        content = await file.read()
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

        from jira_emulator.services.import_service import _unwrap_export_envelope

        issues = _unwrap_export_envelope(data)
        if not issues and not isinstance(data, (list, dict)):
            raise HTTPException(
                status_code=400,
                detail=f"Expected a JSON array or object, got {type(data).__name__}",
            )

        result = await import_issues(db, issues)

    return ImportResponse(
        imported=result.imported,
        updated=result.updated,
        errors=result.errors,
        projects_created=result.projects_created,
        users_created=result.users_created,
    )


@router.post("/import/project-config")
async def import_project_config_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a v1.0 project configuration JSON file."""
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")

    version = data.get("version")
    if version != "1.0":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported config version: {version!r} (expected '1.0')",
        )

    result = await import_project_config(db, data)

    return {
        "statuses": result.statuses,
        "issue_types": result.issue_types,
        "priorities": result.priorities,
        "resolutions": result.resolutions,
        "link_types": result.link_types,
        "custom_fields": result.custom_fields,
        "workflows": result.workflows,
        "projects": result.projects,
        "errors": result.errors,
    }


@router.post("/projects", status_code=201)
async def create_admin_project(
    body: AdminProjectCreateBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a project from the admin API."""
    try:
        project = await create_project(
            db,
            key=body.key,
            name=body.name,
            description=body.description,
            lead=body.lead,
            project_type_key=body.project_type_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _project_response(project)


@router.delete("/projects/{project_key}", status_code=204)
async def delete_admin_project(
    project_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project and its issues from the admin API."""
    result = await delete_project(db, project_key)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project {project_key} not found")
    return Response(status_code=204)


@router.post("/reset")
async def reset_database(
    current_user: User = Depends(get_current_user),
):
    """Reset the database: drop all tables, recreate, and reseed."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = get_session_factory()
    async with factory() as session:
        await load_seed_data(session)

    return {"message": "Database reset successfully"}


# ---- Snapshot endpoints ----


class SnapshotCreateBody(BaseModel):
    label: str | None = None


def _check_snapshots_enabled():
    if not is_snapshot_enabled():
        raise HTTPException(
            status_code=501,
            detail="Snapshots are only available inside the container.",
        )


@router.get("/snapshots")
async def get_snapshots(current_user: User = Depends(get_current_user)):
    """List available snapshots."""
    _check_snapshots_enabled()
    return {"enabled": True, "snapshots": list_snapshots()}


@router.post("/snapshots", status_code=201)
async def post_snapshot(
    body: SnapshotCreateBody | None = None,
    current_user: User = Depends(get_current_user),
):
    """Create a new database snapshot."""
    _check_snapshots_enabled()
    label = body.label if body else None
    info = create_snapshot(label)
    return info


@router.post("/snapshots/{name}/restore")
async def post_restore(name: str, current_user: User = Depends(get_current_user)):
    """Restore a snapshot (restarts the API process)."""
    _check_snapshots_enabled()
    try:
        restore_snapshot(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"message": "Restoring from snapshot. Server is restarting..."}


@router.delete("/snapshots/{name}", status_code=204)
async def delete_snap(name: str, current_user: User = Depends(get_current_user)):
    """Delete a snapshot."""
    _check_snapshots_enabled()
    try:
        delete_snapshot(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(status_code=204)
