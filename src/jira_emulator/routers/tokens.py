"""PAT (Personal Access Token) management endpoints: /rest/pat/latest/tokens."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.api_token import ApiToken
from jira_emulator.models.user import User
from jira_emulator.schemas.auth import CreateTokenRequest
from jira_emulator.services import auth_service

router = APIRouter(prefix="/rest/pat/latest")


def _format_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}+0000"


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


@router.post("/tokens", status_code=201)
async def create_token(
    body: CreateTokenRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new Personal Access Token."""
    try:
        token, raw_token = await auth_service.create_api_token(
            db,
            user=current_user,
            name=body.name,
            expiration_days=body.expirationDuration,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=_jira_error([str(exc)]),
        )

    return {
        "id": str(token.id),
        "name": token.name,
        "createdAt": _format_datetime(token.created_at),
        "expiringAt": _format_datetime(token.expires_at),
        "rawToken": raw_token,
    }


@router.get("/tokens")
async def list_tokens(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tokens for the current user (without raw values)."""
    result = await db.execute(
        select(ApiToken)
        .where(
            ApiToken.user_id == current_user.id,
            ApiToken.active == True,  # noqa: E712
        )
        .order_by(ApiToken.created_at.desc())
    )
    tokens = list(result.scalars().all())

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "createdAt": _format_datetime(t.created_at),
            "expiringAt": _format_datetime(t.expires_at),
            "lastUsedAt": _format_datetime(t.last_used_at),
        }
        for t in tokens
    ]


@router.delete("/tokens/{tokenId}", status_code=204)
async def revoke_token(
    tokenId: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (deactivate) a Personal Access Token."""
    result = await db.execute(
        select(ApiToken).where(
            ApiToken.id == tokenId,
            ApiToken.user_id == current_user.id,
        )
    )
    token = result.scalar_one_or_none()

    if token is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Token with id '{tokenId}' not found."]),
        )

    token.active = False
    await db.flush()

    return Response(status_code=204)
