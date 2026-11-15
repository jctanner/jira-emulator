"""Search request / response Pydantic v2 schemas for the Jira Emulator."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """POST /rest/api/{2,3}/search body (legacy search)."""

    jql: str
    startAt: int = 0
    maxResults: int = 50
    fields: list[str] | None = None
    nextPageToken: str | None = None


class SearchJqlRequest(BaseModel):
    """POST /rest/api/{2,3}/search/jql body (Jira Cloud enhanced search).

    ``expand`` is a comma-separated string here, unlike most Jira APIs.
    ``properties``, ``fieldsByKeys``, ``failFast``, ``reconcileIssues`` and
    ``includeArchivedProjects`` are accepted for compatibility and ignored.
    """

    jql: str = ""
    nextPageToken: str | None = None
    maxResults: int = 50
    fields: list[str] | None = None
    expand: str | None = None
    properties: list[str] | None = None
    fieldsByKeys: bool = False
    failFast: bool = False
    reconcileIssues: list[int] | None = None
    includeArchivedProjects: bool = False


class ApproximateCountRequest(BaseModel):
    """POST /rest/api/{2,3}/search/approximate-count body."""

    jql: str = ""


class SearchResponse(BaseModel):
    """Search results envelope."""

    expand: str = ""
    startAt: int = 0
    maxResults: int = 50
    total: int = 0
    issues: list[dict] = Field(default_factory=list)
