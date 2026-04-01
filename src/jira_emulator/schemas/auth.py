"""Auth, user, and token Pydantic v2 schemas for the Jira Emulator."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---- user management ----

class CreateUserRequest(BaseModel):
    """POST /rest/api/2/user body."""

    name: str
    password: str
    emailAddress: str
    displayName: str
    applicationKeys: list[str] | None = None


class UpdateUserRequest(BaseModel):
    """PUT /rest/api/2/user body (partial updates)."""

    emailAddress: str | None = None
    displayName: str | None = None


class ChangePasswordRequest(BaseModel):
    """PUT /rest/api/2/user/password body."""

    password: str
    currentPassword: str | None = None


# ---- session / cookie auth ----

class SessionLoginRequest(BaseModel):
    """POST /rest/auth/1/session body."""

    username: str
    password: str


class SessionInfo(BaseModel):
    """Session cookie details."""

    name: str
    value: str


class LoginInfo(BaseModel):
    """Login statistics returned alongside the session."""

    failedLoginCount: int = 0
    loginCount: int = 0
    lastFailedLoginTime: str | None = None
    previousLoginTime: str | None = None


class SessionLoginResponse(BaseModel):
    """POST /rest/auth/1/session response."""

    session: SessionInfo
    loginInfo: LoginInfo


# ---- API tokens (PAT) ----

class CreateTokenRequest(BaseModel):
    """POST /rest/pat/latest/tokens body."""

    name: str
    expirationDuration: int | None = None


class CreateTokenResponse(BaseModel):
    """Response after creating a personal-access token."""

    id: str
    name: str
    createdAt: str
    expiringAt: str | None = None
    rawToken: str


class TokenListItem(BaseModel):
    """Single token entry in a list response."""

    id: str
    name: str
    createdAt: str
    expiringAt: str | None = None
    lastUsedAt: str | None = None
