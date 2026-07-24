"""Issue property endpoints: /rest/api/2/issue/{key}/properties."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.database import get_db
from jira_emulator.models.issue_property import IssueProperty
from jira_emulator.models.user import User
from jira_emulator.services import issue_service

router = APIRouter(prefix="/rest/api/2")

MAX_KEY_LENGTH = 255
MAX_VALUE_LENGTH = 32768


def _jira_error(messages: list[str], errors: dict | None = None) -> dict:
    return {"errorMessages": messages, "errors": errors or {}}


async def _resolve_issue(db: AsyncSession, issue_key: str):
    issue = await issue_service.get_issue(db, issue_key)
    if issue is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Issue '{issue_key}' not found"]),
        )
    return issue


@router.get("/issue/{issueIdOrKey}/properties")
async def get_issue_property_keys(
    issueIdOrKey: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the keys of all properties on an issue."""
    issue = await _resolve_issue(db, issueIdOrKey)
    result = await db.execute(select(IssueProperty).where(IssueProperty.issue_id == issue.id))
    props = list(result.scalars().all())

    base = f"{request.base_url}rest/api/2/issue/{issueIdOrKey}/properties"
    return {
        "keys": [
            {"self": f"{base}/{p.key}", "key": p.key}
            for p in props
        ]
    }


@router.get("/issue/{issueIdOrKey}/properties/{propertyKey}")
async def get_issue_property(
    issueIdOrKey: str,
    propertyKey: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the key and value of an issue property."""
    issue = await _resolve_issue(db, issueIdOrKey)
    result = await db.execute(
        select(IssueProperty).where(
            IssueProperty.issue_id == issue.id,
            IssueProperty.key == propertyKey,
        )
    )
    prop = result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Property '{propertyKey}' not found on issue '{issueIdOrKey}'"]),
        )
    return {"key": prop.key, "value": json.loads(prop.value)}


@router.put("/issue/{issueIdOrKey}/properties/{propertyKey}")
async def set_issue_property(
    issueIdOrKey: str,
    propertyKey: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the value of an issue property. Returns 201 on create, 200 on update."""
    issue = await _resolve_issue(db, issueIdOrKey)

    if len(propertyKey) > MAX_KEY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=_jira_error([f"Property key exceeds maximum length of {MAX_KEY_LENGTH} characters"]),
        )

    body = await request.body()
    if not body:
        raise HTTPException(
            status_code=400,
            detail=_jira_error(["The request body must be a valid, non-empty JSON blob"]),
        )

    try:
        json.loads(body)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=_jira_error(["The request body must be valid JSON"]),
        )

    value_str = body.decode("utf-8")
    if len(value_str) > MAX_VALUE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=_jira_error([f"Property value exceeds maximum length of {MAX_VALUE_LENGTH} characters"]),
        )

    result = await db.execute(
        select(IssueProperty).where(
            IssueProperty.issue_id == issue.id,
            IssueProperty.key == propertyKey,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.value = value_str
        await db.flush()
        return Response(status_code=200)

    prop = IssueProperty(issue_id=issue.id, key=propertyKey, value=value_str)
    db.add(prop)
    await db.flush()
    return Response(status_code=201)


@router.delete("/issue/{issueIdOrKey}/properties/{propertyKey}", status_code=204)
async def delete_issue_property(
    issueIdOrKey: str,
    propertyKey: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an issue property."""
    issue = await _resolve_issue(db, issueIdOrKey)
    result = await db.execute(
        select(IssueProperty).where(
            IssueProperty.issue_id == issue.id,
            IssueProperty.key == propertyKey,
        )
    )
    prop = result.scalar_one_or_none()
    if prop is None:
        raise HTTPException(
            status_code=404,
            detail=_jira_error([f"Property '{propertyKey}' not found on issue '{issueIdOrKey}'"]),
        )
    await db.delete(prop)
    await db.flush()
    return Response(status_code=204)
