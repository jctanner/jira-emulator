"""Pydantic v2 request / response schemas for the Jira Emulator."""

from .admin import ImportRequest, ImportResponse
from .auth import (
    ChangePasswordRequest,
    CreateTokenRequest,
    CreateTokenResponse,
    CreateUserRequest,
    LoginInfo,
    SessionInfo,
    SessionLoginRequest,
    SessionLoginResponse,
    TokenListItem,
    UpdateUserRequest,
)
from .comment import CommentResponse, CommentsResponse, CreateCommentRequest
from .common import (
    ComponentRef,
    IssueTypeRef,
    JiraErrorResponse,
    PriorityRef,
    ProjectRef,
    ResolutionRef,
    StatusCategoryRef,
    StatusRef,
    UserRef,
    VersionRef,
)
from .issue import (
    CreateIssueRequest,
    CreateIssueResponse,
    IssueResponse,
    TransitionItem,
    TransitionRequest,
    TransitionsResponse,
    TransitionTarget,
    UpdateIssueRequest,
)
from .search import SearchRequest, SearchResponse

__all__ = [
    # common
    "JiraErrorResponse",
    "UserRef",
    "StatusCategoryRef",
    "StatusRef",
    "PriorityRef",
    "IssueTypeRef",
    "ProjectRef",
    "ResolutionRef",
    "ComponentRef",
    "VersionRef",
    # issue
    "CreateIssueRequest",
    "CreateIssueResponse",
    "UpdateIssueRequest",
    "IssueResponse",
    "TransitionTarget",
    "TransitionItem",
    "TransitionsResponse",
    "TransitionRequest",
    # search
    "SearchRequest",
    "SearchResponse",
    # comment
    "CreateCommentRequest",
    "CommentResponse",
    "CommentsResponse",
    # auth
    "CreateUserRequest",
    "UpdateUserRequest",
    "ChangePasswordRequest",
    "SessionLoginRequest",
    "SessionInfo",
    "LoginInfo",
    "SessionLoginResponse",
    "CreateTokenRequest",
    "CreateTokenResponse",
    "TokenListItem",
    # admin
    "ImportRequest",
    "ImportResponse",
]
