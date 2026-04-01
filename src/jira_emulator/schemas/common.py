"""Shared Pydantic v2 models matching Jira REST API v2 JSON format."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JiraErrorResponse(BaseModel):
    """Standard Jira error envelope."""

    errorMessages: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)


class UserRef(BaseModel):
    """Compact user reference returned in many Jira responses."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    name: str
    displayName: str
    emailAddress: str | None = None
    accountId: str | None = None
    active: bool = True


class StatusCategoryRef(BaseModel):
    """Status category reference (e.g. 'new', 'indeterminate', 'done')."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    key: str
    name: str


class StatusRef(BaseModel):
    """Status reference embedded in issue responses."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    name: str
    statusCategory: StatusCategoryRef | None = None


class PriorityRef(BaseModel):
    """Priority reference."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    name: str
    iconUrl: str | None = None


class IssueTypeRef(BaseModel):
    """Issue type reference."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    name: str
    subtask: bool = False


class ProjectRef(BaseModel):
    """Project reference."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    key: str
    name: str


class ResolutionRef(BaseModel):
    """Resolution reference."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    name: str


class ComponentRef(BaseModel):
    """Component reference."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    name: str


class VersionRef(BaseModel):
    """Version / fixVersion reference."""

    model_config = ConfigDict(populate_by_name=True)

    self_url: str | None = Field(default=None, alias="self")
    id: str
    name: str
