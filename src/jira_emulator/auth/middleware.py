"""Authentication middleware — extracts and validates credentials from requests."""

import base64
import logging

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.user import User
from jira_emulator.services import auth_service
from jira_emulator.services.user_service import get_or_create_user, get_user_by_username

logger = logging.getLogger(__name__)


def _parse_basic_auth(header_value: str) -> tuple[str, str] | None:
    """Parse Basic auth header, return (username_or_email, password) or None."""
    try:
        scheme, _, encoded = header_value.partition(" ")
        if scheme.lower() != "basic":
            return None
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, _, password = decoded.partition(":")
        if not username:
            return None
        return username, password
    except Exception:
        return None


def _parse_bearer_auth(header_value: str) -> str | None:
    """Parse Bearer auth header, return token string or None."""
    try:
        scheme, _, token = header_value.partition(" ")
        if scheme.lower() != "bearer":
            return None
        return token.strip() if token.strip() else None
    except Exception:
        return None


def _extract_username(username_or_email: str) -> str:
    """Extract a username from an email address or return as-is."""
    if "@" in username_or_email:
        return username_or_email.split("@")[0]
    return username_or_email


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency that resolves the current user from the request.

    Behavior depends on AUTH_MODE setting:
    - permissive: accept any auth, extract username, auto-create users
    - strict: validate credentials, return 401 on failure
    - none: no auth required, return default user
    """
    settings = get_settings()
    auth_header = request.headers.get("Authorization", "")

    if settings.AUTH_MODE == "none":
        user = await get_user_by_username(db, settings.DEFAULT_USER)
        if user is None:
            user = await get_or_create_user(db, "Admin User", settings.DEFAULT_USER)
        request.state.user = user
        return user

    if settings.AUTH_MODE == "strict":
        return await _strict_auth(request, db, auth_header, settings)

    # permissive mode (default)
    return await _permissive_auth(request, db, auth_header, settings)


async def _strict_auth(
    request: Request, db: AsyncSession, auth_header: str, settings
) -> User:
    """Strict mode: validate credentials or return 401."""
    basic = _parse_basic_auth(auth_header)
    if basic:
        username_or_email, password = basic
        user = await auth_service.authenticate_basic(db, username_or_email, password)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail={"errorMessages": ["Authentication failed"], "errors": {}},
            )
        request.state.user = user
        return user

    bearer_token = _parse_bearer_auth(auth_header)
    if bearer_token:
        user = await auth_service.validate_api_token(db, bearer_token)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail={"errorMessages": ["Invalid or expired token"], "errors": {}},
            )
        request.state.user = user
        return user

    raise HTTPException(
        status_code=401,
        detail={"errorMessages": ["Authentication required"], "errors": {}},
    )


async def _permissive_auth(
    request: Request, db: AsyncSession, auth_header: str, settings
) -> User:
    """Permissive mode: extract user info but don't validate passwords."""
    basic = _parse_basic_auth(auth_header)
    if basic:
        username_or_email, _ = basic
        username = _extract_username(username_or_email)
        user = await get_or_create_user(db, username, username)
        request.state.user = user
        return user

    bearer_token = _parse_bearer_auth(auth_header)
    if bearer_token:
        user = await auth_service.validate_api_token(db, bearer_token)
        if user:
            request.state.user = user
            return user

    # Fall back to default user
    user = await get_or_create_user(db, "Admin User", settings.DEFAULT_USER)
    request.state.user = user
    return user
