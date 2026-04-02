"""Admin endpoints: /api/admin/import, /api/admin/reset."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.database import Base, get_db, get_engine, get_session_factory
from jira_emulator.models.user import User
from jira_emulator.schemas.admin import ImportRequest, ImportResponse
from jira_emulator.services.import_service import import_issues
from jira_emulator.services.seed_service import load_seed_data

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
