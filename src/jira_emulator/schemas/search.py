"""Search request / response Pydantic v2 schemas for the Jira Emulator."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """POST /rest/api/2/search body."""

    jql: str
    startAt: int = 0
    maxResults: int = 50
    fields: list[str] | None = None


class SearchResponse(BaseModel):
    """Search results envelope."""

    expand: str = ""
    startAt: int = 0
    maxResults: int = 50
    total: int = 0
    issues: list[dict] = Field(default_factory=list)
