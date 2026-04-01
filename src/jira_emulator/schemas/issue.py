"""Issue request / response Pydantic v2 schemas for the Jira Emulator."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# ---- requests ----

class CreateIssueRequest(BaseModel):
    """POST /rest/api/2/issue body."""

    fields: dict


class UpdateIssueRequest(BaseModel):
    """PUT /rest/api/2/issue/{issueIdOrKey} body."""

    fields: dict | None = None
    update: dict | None = None


class TransitionRequest(BaseModel):
    """POST /rest/api/2/issue/{issueIdOrKey}/transitions body."""

    transition: dict
    fields: dict | None = None
    update: dict | None = None


# ---- responses ----

class CreateIssueResponse(BaseModel):
    """Returned after a successful issue creation."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    key: str
    self_url: str | None = Field(default=None, alias="self")


class IssueResponse(BaseModel):
    """Full issue representation (GET /rest/api/2/issue/{key})."""

    model_config = ConfigDict(populate_by_name=True)

    expand: str = ""
    id: str
    self_url: str | None = Field(default=None, alias="self")
    key: str
    fields: dict


class TransitionTarget(BaseModel):
    """The target status of a transition."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    name: str
    statusCategory: dict | None = None


class TransitionItem(BaseModel):
    """A single available transition."""

    id: str
    name: str
    to: TransitionTarget


class TransitionsResponse(BaseModel):
    """GET /rest/api/2/issue/{key}/transitions response."""

    expand: str = ""
    transitions: list[TransitionItem]
