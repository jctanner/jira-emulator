"""Attachment endpoints: /rest/api/2/attachment/... and upload via issue."""

import logging
import mimetypes
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Header
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.attachment import Attachment
from jira_emulator.models.user import User
from jira_emulator.services import issue_service, history_service
from jira_emulator.services.issue_service import _format_user, _format_datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rest/api/2")

_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml", "image/bmp", "image/tiff"}


def _format_attachment(att: Attachment, base_url: str) -> dict:
    is_image = att.mime_type in _IMAGE_TYPES
    result = {
        "self": f"{base_url}/rest/api/2/attachment/{att.id}",
        "id": str(att.id),
        "filename": att.filename,
        "author": _format_user(att.author, base_url),
        "created": _format_datetime(att.created_at),
        "size": att.size,
        "mimeType": att.mime_type,
        "content": f"{base_url}/rest/api/2/attachment/content/{att.id}",
    }
    if is_image:
        result["thumbnail"] = f"{base_url}/rest/api/2/attachment/thumbnail/{att.id}"
    return result


# ---------------------------------------------------------------------------
# POST /issue/{issueIdOrKey}/attachments — Upload files
# ---------------------------------------------------------------------------

@router.post("/issue/{issueIdOrKey}/attachments", status_code=200)
async def upload_attachments(
    issueIdOrKey: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    x_atlassian_token: str | None = Header(default=None, alias="X-Atlassian-Token"),
):
    """Attach one or more files to an issue (multipart/form-data)."""
    settings = get_settings()
    base_url = settings.BASE_URL
    attachment_dir = settings.ATTACHMENT_DIR

    if x_atlassian_token is None:
        logger.warning("X-Atlassian-Token header missing — allowing anyway (emulator permissive mode)")

    issue = await issue_service.get_issue(db, issueIdOrKey)
    if issue is None:
        raise HTTPException(status_code=404, detail={"errorMessages": [f"Issue Does Not Exist: {issueIdOrKey}"], "errors": {}})

    # Parse multipart form data to get uploaded files
    form = await request.form()
    files = form.getlist("file")

    if not files:
        raise HTTPException(status_code=400, detail={"errorMessages": ["No file provided"], "errors": {}})

    os.makedirs(attachment_dir, exist_ok=True)

    results = []
    now = datetime.utcnow()

    for upload in files:
        content = await upload.read()
        filename = upload.filename or "unnamed"
        mime = upload.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        size = len(content)

        attachment = Attachment(
            issue_id=issue.id,
            author_id=current_user.id,
            filename=filename,
            size=size,
            mime_type=mime,
            file_path="",  # placeholder, updated after flush
            created_at=now,
        )
        db.add(attachment)
        await db.flush()

        # Save file to disk
        disk_filename = f"{attachment.id}_{filename}"
        disk_path = os.path.join(attachment_dir, disk_filename)
        attachment.file_path = disk_filename

        with open(disk_path, "wb") as f:
            f.write(content)

        # Eagerly load author for formatting
        result = await db.execute(
            select(Attachment)
            .options(selectinload(Attachment.author))
            .where(Attachment.id == attachment.id)
        )
        att_loaded = result.scalar_one()

        await history_service.record_change(
            db, issue.id, current_user.id, "Attachment",
            None, None, filename, str(attachment.id),
        )

        results.append(_format_attachment(att_loaded, base_url))

    return results


# ---------------------------------------------------------------------------
# GET /attachment/{id} — Attachment metadata
# ---------------------------------------------------------------------------

@router.get("/attachment/{attachment_id}")
async def get_attachment_meta(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    base_url = settings.BASE_URL

    result = await db.execute(
        select(Attachment)
        .options(selectinload(Attachment.author))
        .where(Attachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail={"errorMessages": ["Attachment not found"], "errors": {}})

    return _format_attachment(att, base_url)


# ---------------------------------------------------------------------------
# DELETE /attachment/{id} — Delete attachment
# ---------------------------------------------------------------------------

@router.delete("/attachment/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail={"errorMessages": ["Attachment not found"], "errors": {}})

    # Record history before deletion
    await history_service.record_change(
        db, att.issue_id, current_user.id, "Attachment",
        att.filename, str(att.id), None, None,
    )

    # Remove file from disk
    disk_path = os.path.join(settings.ATTACHMENT_DIR, att.file_path)
    if os.path.exists(disk_path):
        os.remove(disk_path)

    await db.delete(att)
    await db.flush()

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GET /attachment/content/{id} — Download file
# ---------------------------------------------------------------------------

@router.get("/attachment/content/{attachment_id}")
async def get_attachment_content(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail={"errorMessages": ["Attachment not found"], "errors": {}})

    disk_path = os.path.join(settings.ATTACHMENT_DIR, att.file_path)
    if not os.path.exists(disk_path):
        raise HTTPException(status_code=404, detail={"errorMessages": ["Attachment file missing from disk"], "errors": {}})

    return FileResponse(
        path=disk_path,
        media_type=att.mime_type,
        filename=att.filename,
        headers={"Content-Disposition": f'attachment; filename="{att.filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /attachment/thumbnail/{id} — Thumbnail (simplified: returns file for images)
# ---------------------------------------------------------------------------

@router.get("/attachment/thumbnail/{attachment_id}")
async def get_attachment_thumbnail(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail={"errorMessages": ["Attachment not found"], "errors": {}})

    if att.mime_type not in _IMAGE_TYPES:
        raise HTTPException(status_code=404, detail={"errorMessages": ["No thumbnail available for non-image attachment"], "errors": {}})

    disk_path = os.path.join(settings.ATTACHMENT_DIR, att.file_path)
    if not os.path.exists(disk_path):
        raise HTTPException(status_code=404, detail={"errorMessages": ["Attachment file missing from disk"], "errors": {}})

    return FileResponse(path=disk_path, media_type=att.mime_type)


# ---------------------------------------------------------------------------
# GET /attachment/meta — Attachment capabilities
# ---------------------------------------------------------------------------

@router.get("/attachment/meta")
async def get_attachment_meta_info(
    current_user: User = Depends(get_current_user),
):
    return {"enabled": True, "uploadLimit": 10485760}
