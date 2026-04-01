"""Comment request / response Pydantic v2 schemas for the Jira Emulator."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateCommentRequest(BaseModel):
    """POST /rest/api/2/issue/{issueIdOrKey}/comment body."""

    body: str
    visibility: dict | None = None


class CommentResponse(BaseModel):
    """Single comment representation."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    author: dict
    body: str
    created: str
    updated: str


class CommentsResponse(BaseModel):
    """Paginated list of comments."""

    startAt: int = 0
    maxResults: int = 50
    total: int = 0
    comments: list[dict] = Field(default_factory=list)
