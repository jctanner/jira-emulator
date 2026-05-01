"""Admin endpoints: /api/admin/import, /api/admin/reset, /api/admin/snapshots."""

import json
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.database import Base, get_db, get_engine, get_session_factory
from jira_emulator.models.user import User
from jira_emulator.schemas.admin import ImportRequest, ImportResponse
from jira_emulator.services.import_service import import_archive, import_issues
from jira_emulator.services.seed_service import load_seed_data
from jira_emulator.services.snapshot_service import (
    create_snapshot,
    delete_snapshot,
    is_snapshot_enabled,
    list_snapshots,
    restore_snapshot,
)

router = APIRouter(prefix="/api/admin")


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

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            raise HTTPException(
                status_code=400,
                detail=f"Expected a JSON array or object, got {type(data).__name__}",
            )

        result = await import_issues(db, data)

    return ImportResponse(
        imported=result.imported,
        updated=result.updated,
        errors=result.errors,
        projects_created=result.projects_created,
        users_created=result.users_created,
    )


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
