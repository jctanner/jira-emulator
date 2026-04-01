"""User management endpoints: /rest/api/2/user."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.user import User
from jira_emulator.schemas.auth import (
    ChangePasswordRequest,
    CreateUserRequest,
    UpdateUserRequest,
)
from jira_emulator.services import auth_service
from jira_emulator.services import user_service

router = APIRouter()


def _format_user(user: User, base_url: str) -> dict:
    return {
        "self": f"{base_url}/rest/api/2/user?username={user.username}",
        "key": user.username,
        "name": user.username,
        "emailAddress": user.email or "",
        "displayName": user.display_name,
        "active": user.active,
        "accountId": str(user.id),
        "timeZone": "UTC",
        "locale": "en_US",
    }


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


@router.post("/rest/api/2/user", status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user."""
    settings = get_settings()
    base_url = settings.BASE_URL

    # Check if user already exists
    existing = await user_service.get_user_by_username(db, body.name)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=_jira_error(
                [f"A user with username '{body.name}' already exists."]
            ),
        )

    user = await user_service.create_user(
        db,
        username=body.name,
        display_name=body.displayName,
        email=body.emailAddress,
        password=body.password,
    )

    return _format_user(user, base_url)


@router.get("/rest/api/2/user")
async def get_user(
    username: str = Query(...),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a user by username."""
    settings = get_settings()
    base_url = settings.BASE_URL

    user = await user_service.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"User '{username}' does not exist."]),
        )

    return _format_user(user, base_url)


@router.put("/rest/api/2/user")
async def update_user(
    body: UpdateUserRequest,
    username: str = Query(...),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's email and/or display name."""
    settings = get_settings()
    base_url = settings.BASE_URL

    user = await user_service.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"User '{username}' does not exist."]),
        )

    user = await user_service.update_user(
        db,
        user,
        email=body.emailAddress,
        display_name=body.displayName,
    )

    return _format_user(user, base_url)


@router.put("/rest/api/2/user/password")
async def admin_change_password(
    body: ChangePasswordRequest,
    username: str = Query(...),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: change a user's password."""
    user = await user_service.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"User '{username}' does not exist."]),
        )

    # Admin password change: no current password required
    success = await auth_service.change_password(
        db,
        user,
        new_password=body.password,
        current_password=None,
    )
    if not success:
        raise HTTPException(
            status_code=400,
            detail=_jira_error(["Failed to change password."]),
        )

    return Response(status_code=204)


@router.get("/rest/api/2/user/assignable/search")
async def search_assignable_users(
    request: Request,
    project: str | None = Query(default=None),
    username: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for users that can be assigned to issues."""
    settings = get_settings()
    base_url = settings.BASE_URL

    users = await user_service.search_assignable_users(
        db, project=project, username=username
    )

    return [_format_user(u, base_url) for u in users]
