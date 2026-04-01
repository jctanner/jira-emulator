"""Authentication endpoints: /rest/api/2/myself and /rest/auth/1/session."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.user import User
from jira_emulator.services import auth_service
from jira_emulator.services.user_service import get_user_by_username
from jira_emulator.schemas.auth import (
    ChangePasswordRequest,
    SessionLoginRequest,
    SessionLoginResponse,
    SessionInfo,
    LoginInfo,
)

router = APIRouter()

# In-memory session store: session_id -> user_id
_sessions: dict[str, int] = {}


def _format_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}+0000"


# ---- /rest/api/2/myself ----


@router.get("/rest/api/2/myself")
async def get_myself(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Return the currently authenticated user."""
    settings = get_settings()
    base_url = settings.BASE_URL
    return {
        "self": f"{base_url}/rest/api/2/user?username={current_user.username}",
        "key": current_user.username,
        "name": current_user.username,
        "emailAddress": current_user.email or "",
        "displayName": current_user.display_name,
        "active": current_user.active,
        "accountId": str(current_user.id),
        "timeZone": "UTC",
        "locale": "en_US",
    }


@router.put("/rest/api/2/myself/password")
async def change_own_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's own password."""
    success = await auth_service.change_password(
        db,
        current_user,
        new_password=body.password,
        current_password=body.currentPassword,
    )
    if not success:
        raise HTTPException(
            status_code=403,
            detail={"errorMessages": ["Current password is incorrect"], "errors": {}},
        )
    return Response(status_code=204)


# ---- /rest/auth/1/session ----


@router.post("/rest/auth/1/session")
async def session_login(
    body: SessionLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Cookie-based login. Validates credentials and returns a session token."""
    settings = get_settings()

    if settings.AUTH_MODE == "none":
        # In 'none' mode, accept any login
        user = await get_user_by_username(db, body.username)
        if user is None:
            from jira_emulator.services.user_service import get_or_create_user
            user = await get_or_create_user(db, body.username, body.username)
    elif settings.AUTH_MODE == "permissive":
        # In permissive mode, auto-create but don't validate password
        from jira_emulator.services.user_service import get_or_create_user
        user = await get_or_create_user(db, body.username, body.username)
    else:
        # strict mode: validate credentials
        user = await auth_service.authenticate_basic(db, body.username, body.password)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "errorMessages": [
                        "Login failed. Check your username and password and try again."
                    ],
                    "errors": {},
                },
            )

    session_id = str(uuid.uuid4())
    _sessions[session_id] = user.id

    response = SessionLoginResponse(
        session=SessionInfo(name="JSESSIONID", value=session_id),
        loginInfo=LoginInfo(
            failedLoginCount=0,
            loginCount=1,
            lastFailedLoginTime=None,
            previousLoginTime=_format_datetime(datetime.utcnow()),
        ),
    )
    return response.model_dump()


@router.get("/rest/auth/1/session")
async def get_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return the current session user, or 401 if not authenticated."""
    settings = get_settings()
    base_url = settings.BASE_URL

    # Check for JSESSIONID cookie
    session_id = request.cookies.get("JSESSIONID")
    if session_id and session_id in _sessions:
        user_id = _sessions[session_id]
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            return {
                "self": f"{base_url}/rest/api/2/user?username={user.username}",
                "name": user.username,
                "loginInfo": {
                    "failedLoginCount": 0,
                    "loginCount": 1,
                    "lastFailedLoginTime": None,
                    "previousLoginTime": _format_datetime(datetime.utcnow()),
                },
            }

    # Fall back to standard auth header
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        try:
            current_user = await get_current_user(request, db)
            return {
                "self": f"{base_url}/rest/api/2/user?username={current_user.username}",
                "name": current_user.username,
                "loginInfo": {
                    "failedLoginCount": 0,
                    "loginCount": 1,
                    "lastFailedLoginTime": None,
                    "previousLoginTime": _format_datetime(datetime.utcnow()),
                },
            }
        except HTTPException:
            pass

    raise HTTPException(
        status_code=401,
        detail={
            "errorMessages": ["You are not authenticated. Please log in."],
            "errors": {},
        },
    )


@router.delete("/rest/auth/1/session")
async def session_logout(request: Request):
    """Logout: remove the session."""
    session_id = request.cookies.get("JSESSIONID")
    if session_id and session_id in _sessions:
        del _sessions[session_id]
    return Response(status_code=204)
