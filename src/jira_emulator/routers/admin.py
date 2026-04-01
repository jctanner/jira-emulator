"""Admin endpoints: /api/admin/import."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.database import get_db
from jira_emulator.models.user import User
from jira_emulator.schemas.admin import ImportRequest, ImportResponse
from jira_emulator.services.import_service import import_issues

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
