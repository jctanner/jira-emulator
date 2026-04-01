"""Admin / import Pydantic v2 schemas for the Jira Emulator."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    """POST /admin/import body."""

    issues: list[dict]


class ImportResponse(BaseModel):
    """Import result summary."""

    imported: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)
    projects_created: list[str] = Field(default_factory=list)
    users_created: list[str] = Field(default_factory=list)
