# Jira Emulator — Implementation Plan

**Date:** March 31, 2026
**Status:** Ready for implementation
**Spec:** [SPECIFICATION.md](./SPECIFICATION.md)

---

## Project Structure

```
jira-emulator/
├── SPECIFICATION.md
├── PLAN.md
├── Dockerfile
├── Containerfile                  # Alias for Podman users
├── requirements.txt
├── pyproject.toml
├── seed.yaml                     # Default seed data configuration
├── src/
│   └── jira_emulator/
│       ├── __init__.py
│       ├── __main__.py           # CLI entry point (serve, import)
│       ├── app.py                # FastAPI application factory
│       ├── config.py             # Settings from env vars
│       ├── database.py           # SQLAlchemy async engine + session
│       ├── models/
│       │   ├── __init__.py
│       │   ├── project.py        # Project, ProjectIssueType, ProjectWorkflow
│       │   ├── issue.py          # Issue, IssueSequence
│       │   ├── issue_type.py     # IssueType
│       │   ├── status.py         # Status
│       │   ├── priority.py       # Priority
│       │   ├── resolution.py     # Resolution
│       │   ├── user.py           # User (with password_hash)
│       │   ├── api_token.py      # ApiToken (PATs and API tokens)
│       │   ├── comment.py        # Comment
│       │   ├── label.py          # Label
│       │   ├── component.py      # Component, IssueComponent
│       │   ├── version.py        # Version, IssueFixVersion, IssueAffectsVersion
│       │   ├── workflow.py       # Workflow, WorkflowTransition
│       │   ├── link.py           # IssueLink, IssueLinkType
│       │   ├── watcher.py        # Watcher
│       │   ├── custom_field.py   # CustomField, IssueCustomFieldValue
│       │   └── sprint.py         # Sprint, IssueSprint
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── issue.py          # Pydantic request/response models for issues
│       │   ├── project.py        # Pydantic models for projects
│       │   ├── search.py         # Search request/response models
│       │   ├── comment.py        # Comment models
│       │   ├── common.py         # Shared models (error response, user ref, etc.)
│       │   ├── auth.py           # Auth request/response models (login, token, password)
│       │   └── admin.py          # Import request/response models
│       ├── services/
│       │   ├── __init__.py
│       │   ├── issue_service.py      # Issue CRUD + update operations
│       │   ├── project_service.py    # Project lookups
│       │   ├── search_service.py     # JQL search orchestration
│       │   ├── workflow_service.py   # Transition logic
│       │   ├── import_service.py     # JSON import with auto-entity creation
│       │   ├── user_service.py       # User CRUD + auto-creation
│       │   ├── auth_service.py       # Password hashing, token generation/validation
│       │   └── seed_service.py       # Seed data loader
│       ├── jql/
│       │   ├── __init__.py
│       │   ├── grammar.py        # Lark EBNF grammar definition
│       │   ├── parser.py         # JQL string → AST
│       │   ├── transformer.py    # AST → SQLAlchemy filter expressions
│       │   └── functions.py      # JQL function implementations
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── issues.py         # /rest/api/2/issue/...
│       │   ├── search.py         # /rest/api/2/search
│       │   ├── projects.py       # /rest/api/2/project/...
│       │   ├── fields.py         # /rest/api/2/field
│       │   ├── metadata.py       # /rest/api/2/priority, status, resolution, issuetype
│       │   ├── links.py          # /rest/api/2/issueLink, issueLinkType
│       │   ├── auth.py           # /rest/api/2/myself, /rest/auth/1/session
│       │   ├── users.py          # /rest/api/2/user (CRUD + password)
│       │   ├── tokens.py         # /rest/pat/latest/tokens (PAT management)
│       │   └── admin.py          # /api/admin/import
│       ├── auth/
│       │   ├── __init__.py
│       │   └── middleware.py     # Auth extraction (Basic/Bearer/None)
│       └── web/
│           ├── __init__.py
│           ├── routes.py         # Web UI routes (/, /project/{key}, /issues, /issue/{key})
│           ├── templates/
│           │   ├── base.html
│           │   ├── home.html
│           │   ├── project.html
│           │   ├── issues.html
│           │   ├── issue_detail.html
│           │   └── admin_import.html
│           └── static/
│               └── style.css     # Minimal overrides on top of Pico CSS
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Shared fixtures (async client, test DB, seeded data)
│   ├── test_issues.py            # Issue CRUD API tests
│   ├── test_search.py            # JQL search tests
│   ├── test_jql_parser.py        # JQL grammar unit tests
│   ├── test_transitions.py       # Workflow transition tests
│   ├── test_comments.py          # Comment API tests
│   ├── test_projects.py          # Project API tests
│   ├── test_links.py             # Issue link tests
│   ├── test_watchers.py          # Watcher tests
│   ├── test_import.py            # JSON import tests
│   ├── test_metadata.py          # Priority/status/resolution/issuetype endpoints
│   ├── test_auth.py              # Authentication mode tests (Basic, Bearer, session)
│   ├── test_users.py             # User CRUD + password management tests
│   ├── test_tokens.py            # PAT create/list/revoke/authenticate tests
│   └── test_client_compat.py     # Tests using actual assistant_mcp client patterns
└── references/                   # (existing) API reference docs
```

---

## Phase 1: Core API + SQLite (MVP)

**Goal:** Working REST API that `jira-python` / `JiraClientWrapper` can authenticate against, search, get, create, and update issues.

### Step 1.1 — Project bootstrap

**Files:** `pyproject.toml`, `requirements.txt`, `src/jira_emulator/__init__.py`

- Create `pyproject.toml` with project metadata (name: `jira-emulator`, version: `0.1.0`, Python `>=3.11`)
- Dependencies:
  - `fastapi>=0.110`
  - `uvicorn[standard]>=0.27`
  - `sqlalchemy[asyncio]>=2.0`
  - `aiosqlite>=0.20`
  - `pydantic>=2.5`
  - `pydantic-settings>=2.1`
  - `lark>=1.1`
  - `jinja2>=3.1`
  - `pyyaml>=6.0`
  - `bcrypt>=4.1` (password hashing for user auth and token storage)
  - `python-multipart>=0.0.7` (for file upload in web UI)
- Dev dependencies:
  - `pytest>=8.0`
  - `pytest-asyncio>=0.23`
  - `httpx>=0.27`
- Generate `requirements.txt` from the same list
- Create package `__init__.py` with `__version__ = "0.1.0"`

### Step 1.2 — Configuration

**Files:** `src/jira_emulator/config.py`

- Use `pydantic-settings.BaseSettings` to load from env vars:
  - `DATABASE_URL: str = "sqlite+aiosqlite:///data/jira.db"`
  - `HOST: str = "0.0.0.0"`
  - `PORT: int = 8080`
  - `AUTH_MODE: Literal["permissive", "strict", "none"] = "permissive"`
  - `IMPORT_ON_STARTUP: bool = False`
  - `IMPORT_DIR: str = "/data/import"`
  - `BASE_URL: str = "http://localhost:8080"`
  - `DEFAULT_USER: str = "admin"`
  - `LOG_LEVEL: str = "INFO"`
  - `SEED_DATA: bool = True`
  - `ADMIN_PASSWORD: str = "admin"` (default password for seeded admin user; change in production)
- Singleton `get_settings()` function

### Step 1.3 — Database setup

**Files:** `src/jira_emulator/database.py`

- Create async SQLAlchemy engine from `DATABASE_URL`
- `AsyncSessionLocal` session factory
- `get_db()` async dependency for FastAPI
- `init_db()` async function: `Base.metadata.create_all()`
- Use `DeclarativeBase` from SQLAlchemy 2.0
- Enable WAL mode for SQLite: `PRAGMA journal_mode=WAL`
- Enable foreign keys: `PRAGMA foreign_keys=ON`

### Step 1.4 — SQLAlchemy models

**Files:** `src/jira_emulator/models/*.py`

Create all ORM models matching the SQL schema in SPECIFICATION.md §4.1:

- **`models/project.py`**: `Project` (id, key, name, description, lead, project_type_key, created_at, updated_at), `ProjectIssueType` (project_id, issue_type_id), `ProjectWorkflow` (project_id, issue_type_id, workflow_id)
- **`models/issue_type.py`**: `IssueType` (id, name, description, subtask, icon_url)
- **`models/status.py`**: `Status` (id, name, description, category)
- **`models/priority.py`**: `Priority` (id, name, icon_url, sort_order)
- **`models/resolution.py`**: `Resolution` (id, name, description)
- **`models/user.py`**: `User` (id, username, display_name, email, password_hash, active, created_at)
- **`models/api_token.py`**: `ApiToken` (id, user_id, name, token_hash, token_prefix, created_at, expires_at, last_used_at, active) — unique(user_id, name)
- **`models/issue.py`**: `Issue` (all columns from spec), `IssueSequence` (project_id, next_number)
- **`models/comment.py`**: `Comment` (id, issue_id, author_id, body, visibility_type, visibility_value, created_at, updated_at)
- **`models/label.py`**: `Label` (id, issue_id, label) — unique(issue_id, label)
- **`models/component.py`**: `Component` (id, project_id, name, description, lead), `IssueComponent` (issue_id, component_id)
- **`models/version.py`**: `Version` (id, project_id, name, description, released, release_date, start_date, sort_order), `IssueFixVersion`, `IssueAffectsVersion`
- **`models/workflow.py`**: `Workflow` (id, name, description), `WorkflowTransition` (id, workflow_id, name, from_status_id, to_status_id)
- **`models/link.py`**: `IssueLinkType` (id, name, inward_description, outward_description), `IssueLink` (id, link_type_id, inward_issue_id, outward_issue_id)
- **`models/watcher.py`**: `Watcher` (issue_id, user_id)
- **`models/custom_field.py`**: `CustomField` (id, field_id, name, field_type, description), `IssueCustomFieldValue` (id, issue_id, custom_field_id, value_string, value_number, value_date, value_json)
- **`models/sprint.py`**: `Sprint` (id, name, state, start_date, end_date, board_id), `IssueSprint` (issue_id, sprint_id)
- **`models/__init__.py`**: Import all models so `Base.metadata` knows them

### Step 1.5 — Seed data service

**Files:** `src/jira_emulator/services/seed_service.py`, `seed.yaml`

- On first run (empty DB), populate reference data:
  - 4 projects (RHAIRFE, RHAISTRAT, RHOAIENG, AIPCC) with descriptions
  - 8 issue types (Feature Request, Feature, Initiative, Bug, Task, Story, Epic, Sub-task)
  - Project ↔ issue type associations per spec §4.3
  - 6 priorities (Blocker through Undefined with sort_order)
  - 14 statuses with categories (New, Backlog, To Do, ... Closed)
  - 5 resolutions (Done, Won't Do, Duplicate, Cannot Reproduce, Incomplete)
  - 4 issue link types (Blocks, Cloners, Duplicate, Relates)
  - 3 workflows (RHAIRFE, RHAISTRAT, Default) with all transitions from spec §7
  - Project ↔ workflow associations
  - 7 custom fields (Story Points, Team, Target Start/End, Affects Testing, Release Blocker, Severity)
  - Default admin user (admin / Admin User / admin@example.com / password: `admin`) with bcrypt-hashed password
  - Issue sequences initialized for each project (next_number = 1)
- Load from `seed.yaml` if present, otherwise use hardcoded defaults
- Hash the admin user's password with bcrypt before storing
- Check if seed data exists before inserting (idempotent)

### Step 1.6 — Auth service and middleware

**Files:** `src/jira_emulator/services/auth_service.py`, `src/jira_emulator/auth/middleware.py`, `src/jira_emulator/auth/__init__.py`

**Reference:** [references/jira-authentication-specification.md](./references/jira-authentication-specification.md)

#### Auth service (`services/auth_service.py`)

- `hash_password(password: str) -> str`: Hash password with bcrypt
- `verify_password(password: str, password_hash: str) -> bool`: Verify password against bcrypt hash
- `generate_token() -> str`: Generate cryptographically secure random token via `secrets.token_urlsafe(32)`
- `hash_token(raw_token: str) -> str`: Hash a raw API token with bcrypt for storage
- `verify_token(raw_token: str, token_hash: str) -> bool`: Verify a raw token against its stored hash
- `create_api_token(db, user, name, expiration_days=None) -> (ApiToken, raw_token)`:
  - Generate raw token
  - Store bcrypt hash + first 8 chars as prefix
  - Return model + raw token (raw token is only available at creation)
- `validate_api_token(db, raw_token) -> User | None`:
  - Look up all active, non-expired tokens
  - Verify hash match
  - Update `last_used_at`
  - Return the token owner's User, or None
- `authenticate_basic(db, username_or_email, password) -> User | None`:
  - Look up user by username or email
  - Verify password hash
  - Return User or None
- `change_password(db, user, new_password, current_password=None) -> bool`:
  - If `current_password` provided, verify it first
  - Hash and store new password

#### Auth middleware (`auth/middleware.py`)

- FastAPI dependency `get_current_user(request: Request, db: AsyncSession) -> User`:

  **Strict mode** (`AUTH_MODE=strict`):
  - Parse `Authorization` header
  - If `Basic`: decode base64 → `username:password`, call `authenticate_basic()` → 401 if invalid
  - If `Bearer`: extract token, call `validate_api_token()` → 401 if invalid
  - No header → 401
  - Return authenticated `User`

  **Permissive mode** (`AUTH_MODE=permissive`, default):
  - Parse `Authorization` header
  - If `Basic`: decode base64 → extract username (before `:` or email before `@`), look up or auto-create user. Password NOT checked.
  - If `Bearer`: attempt `validate_api_token()`; if no match, use default user.
  - No header → use default user
  - Always succeed, return `User`

  **None mode** (`AUTH_MODE=none`):
  - No header required, return default user for all requests

- Store user on `request.state.user` for downstream access

### Step 1.7 — Pydantic schemas

**Files:** `src/jira_emulator/schemas/*.py`

Define request/response models that match Jira API v2 JSON format exactly:

- **`schemas/common.py`**:
  - `JiraErrorResponse` (errorMessages: list[str], errors: dict[str, str])
  - `UserRef` (self, name, displayName, emailAddress, accountId, active)
  - `StatusRef` (self, id, name, statusCategory: {id, key, name})
  - `PriorityRef` (self, id, name, iconUrl)
  - `IssueTypeRef` (self, id, name, subtask)
  - `ProjectRef` (self, id, key, name)
  - `ResolutionRef` (self, id, name)
  - `ComponentRef` (self, id, name)
  - `VersionRef` (self, id, name)
- **`schemas/issue.py`**:
  - `CreateIssueRequest` (fields: dict)
  - `CreateIssueResponse` (id, key, self)
  - `UpdateIssueRequest` (fields: dict | None, update: dict | None)
  - `IssueResponse` (expand, id, self, key, fields: dict)
  - `TransitionRequest` (transition: {id}, fields, update)
  - `TransitionsResponse` (expand, transitions: list)
- **`schemas/search.py`**:
  - `SearchRequest` (jql, startAt, maxResults, fields)
  - `SearchResponse` (expand, startAt, maxResults, total, issues)
- **`schemas/comment.py`**:
  - `CreateCommentRequest` (body, visibility)
  - `CommentResponse` (self, id, author, body, created, updated)
  - `CommentsResponse` (startAt, maxResults, total, comments)
- **`schemas/auth.py`**:
  - `CreateUserRequest` (name, password, emailAddress, displayName, applicationKeys)
  - `UpdateUserRequest` (emailAddress, displayName)
  - `ChangePasswordRequest` (password, currentPassword — currentPassword optional for admins)
  - `SessionLoginRequest` (username, password)
  - `SessionLoginResponse` (session: {name, value}, loginInfo: {failedLoginCount, loginCount, ...})
  - `CreateTokenRequest` (name, expirationDuration)
  - `CreateTokenResponse` (id, name, createdAt, expiringAt, rawToken)
  - `TokenListItem` (id, name, createdAt, expiringAt, lastUsedAt — no raw token)
- **`schemas/admin.py`**:
  - `ImportRequest` (issues: list[dict])
  - `ImportResponse` (imported, updated, errors, projects_created, users_created)

### Step 1.8 — User service

**Files:** `src/jira_emulator/services/user_service.py`

- `get_user_by_username(db, username)` → User | None
- `get_user_by_email(db, email)` → User | None
- `get_or_create_user(db, display_name, username=None, password=None)` → User
  - If `username` is None, slugify `display_name` (lowercase, replace spaces with `.`)
  - If user exists, return it; else create with generated email
  - If `password` provided, hash it via `auth_service.hash_password()` and store in `password_hash`
  - If no password provided (e.g., auto-creation during import), set `password_hash = None` (user can't log in with Basic auth until password is set)
- `create_user(db, username, display_name, email, password)` → User
  - Validate username uniqueness
  - Hash password, store in `password_hash`
  - Return created User
- `update_user(db, username, email=None, display_name=None)` → User
- `list_users(db)` → list[User]

### Step 1.9 — Issue service

**Files:** `src/jira_emulator/services/issue_service.py`

- `create_issue(db, fields, current_user)` → Issue
  - Validate project exists
  - Validate issue type exists and is allowed for project
  - Allocate next issue key via `issue_sequences`
  - Resolve assignee/reporter via user_service (auto-create if needed)
  - Look up priority (default to first if not specified)
  - Set initial status to first status in project's workflow
  - Store labels, components, custom fields
  - Return the created issue
- `get_issue(db, issue_id_or_key)` → Issue | None
  - Look up by key (string containing `-`) or numeric ID
  - Eager-load: project, status, priority, issue_type, assignee, reporter, resolution, parent, labels, components, fix_versions, affects_versions, comments, issue_links, custom_field_values, watchers
- `update_issue(db, issue_id_or_key, fields, update_ops)` → Issue
  - Handle `fields` dict: direct set of summary, description, priority, assignee, etc.
  - Handle `update` dict: `add`/`remove`/`set` verbs for labels, components, comments
  - Update `updated_at`
- `delete_issue(db, issue_id_or_key)` → bool
  - Cascade delete handled by FK constraints
- `format_issue_response(issue, base_url, fields_filter=None)` → dict
  - Build the full Jira-compatible JSON response structure
  - Include all standard fields + custom fields
  - Apply `fields` filter if specified
  - Format dates as `"2026-01-15T10:30:00.000+0000"`
  - Build `self` URLs using `base_url`

### Step 1.10 — Project service

**Files:** `src/jira_emulator/services/project_service.py`

- `list_projects(db)` → list[Project]
- `get_project(db, key_or_id)` → Project | None
  - Include components, versions, issue types

### Step 1.11 — Basic JQL parser (subset)

**Files:** `src/jira_emulator/jql/grammar.py`, `src/jira_emulator/jql/parser.py`, `src/jira_emulator/jql/transformer.py`, `src/jira_emulator/jql/functions.py`

**Phase 1 subset** — enough for `JiraClientWrapper.search_issues()`:

- **Grammar** (Lark EBNF):
  - Clauses connected by AND / OR
  - NOT prefix
  - Parenthesized grouping
  - Operators: `=`, `!=`, `~`, `!~`, `IN`, `NOT IN`, `IS EMPTY`, `IS NOT EMPTY`
  - ORDER BY field ASC/DESC (multiple fields)
  - Values: quoted strings, unquoted identifiers, numbers, value lists `(a, b, c)`, `EMPTY`/`NULL`
  - Function calls: `currentUser()`
- **Parser**: `lark.Lark` instance with the grammar, `parse(jql_string)` → Tree
- **Transformer**: Walk the Lark tree, emit SQLAlchemy `select()` with filters
  - Field mapping dict: `{"project": ..., "status": ..., "assignee": ..., ...}`
  - Each field maps to a lambda/function that generates the appropriate SQLAlchemy clause
  - Handle joined fields (labels, components) via EXISTS subqueries
  - Handle text search (`~`) via LIKE with COLLATE NOCASE
  - Handle `IS EMPTY` / `IS NOT EMPTY` → IS NULL / IS NOT NULL
  - Handle ORDER BY → `.order_by()`
- **Functions**: `currentUser()` resolves to the authenticated user's username

### Step 1.12 — Search service

**Files:** `src/jira_emulator/services/search_service.py`

- `search_issues(db, jql, start_at, max_results, fields_filter, current_user)`:
  - Parse JQL via `jql.parser.parse()`
  - Transform to SQLAlchemy query via `jql.transformer.transform()`
  - Execute count query for `total`
  - Apply `OFFSET` / `LIMIT` for pagination
  - Format each issue via `issue_service.format_issue_response()`
  - Return `SearchResponse`

### Step 1.13 — API routers

**Files:** `src/jira_emulator/routers/*.py`

#### `routers/auth.py`
- `GET /rest/api/2/myself` → return current authenticated user as JSON
- `PUT /rest/api/2/myself/password` → change own password (requires `currentPassword` + `password`)
- `POST /rest/auth/1/session` → cookie-based login (accepts `{username, password}`, returns `{session: {name, value}, loginInfo}`)
- `GET /rest/auth/1/session` → get current session info (returns user or 401)
- `DELETE /rest/auth/1/session` → logout (invalidate session cookie)

#### `routers/issues.py`
- `POST /rest/api/2/issue` → create issue (201)
- `GET /rest/api/2/issue/{issueIdOrKey}` → get issue (200 / 404)
  - Query params: `fields`, `expand`
- `PUT /rest/api/2/issue/{issueIdOrKey}` → update issue (204 / 404)
- `DELETE /rest/api/2/issue/{issueIdOrKey}` → delete issue (204 / 404)
- `GET /rest/api/2/issue/{issueIdOrKey}/comment` → list comments (200)
- `POST /rest/api/2/issue/{issueIdOrKey}/comment` → add comment (201)

#### `routers/search.py`
- `POST /rest/api/2/search` → search via JQL (200)
- `GET /rest/api/2/search` → search via JQL query params (200)

#### `routers/projects.py`
- `GET /rest/api/2/project` → list projects (200)
- `GET /rest/api/2/project/{projectIdOrKey}` → get project (200 / 404)

#### `routers/metadata.py`
- `GET /rest/api/2/priority` → list priorities
- `GET /rest/api/2/status` → list statuses
- `GET /rest/api/2/resolution` → list resolutions
- `GET /rest/api/2/issuetype` → list issue types

#### `routers/fields.py`
- `GET /rest/api/2/field` → list all fields (system + custom)

#### `routers/users.py`
- `POST /rest/api/2/user` → create user (name, password, emailAddress, displayName) → 201
- `GET /rest/api/2/user?username=X` → get user details → 200 / 404
- `PUT /rest/api/2/user?username=X` → update user (emailAddress, displayName) → 200
- `PUT /rest/api/2/user/password?username=X` → admin: change another user's password → 204
- `GET /rest/api/2/user/assignable/search` → search assignable users (query params: project, username)

#### `routers/tokens.py`
- `POST /rest/pat/latest/tokens` → create PAT (name, expirationDuration) → returns `{id, name, createdAt, expiringAt, rawToken}` (raw token only shown once)
- `GET /rest/pat/latest/tokens` → list current user's tokens (no raw tokens in response)
- `DELETE /rest/pat/latest/tokens/{tokenId}` → revoke a token → 204

All error responses use Jira error format: `{"errorMessages": [...], "errors": {...}}`

### Step 1.14 — FastAPI application factory

**Files:** `src/jira_emulator/app.py`

- Create FastAPI app with title "Jira Emulator", version from package
- Register all routers
- Add startup event:
  1. Call `init_db()` to create tables
  2. If `SEED_DATA` is True and DB is empty, call `seed_service.load_seed_data()`
  3. If `IMPORT_ON_STARTUP` is True, call `import_service.import_directory()`
- Add exception handlers for consistent error responses
- Add CORS middleware (allow all origins for dev)

### Step 1.15 — CLI entry point

**Files:** `src/jira_emulator/__main__.py`

- `python -m jira_emulator serve [--host] [--port] [--reload]` → start uvicorn
- `python -m jira_emulator import <path>` → run import (implemented in Phase 3, stubbed here)
- Use `argparse` for CLI parsing

### Step 1.16 — Dockerfile

**Files:** `Dockerfile`

- Based on `python:3.11-slim`
- Copy requirements, install deps
- Copy source
- Create `/data` directory
- Set environment defaults
- CMD: `python -m jira_emulator serve`

### Step 1.17 — Phase 1 tests

**Files:** `tests/conftest.py`, `tests/test_issues.py`, `tests/test_search.py`, `tests/test_projects.py`, `tests/test_metadata.py`, `tests/test_auth.py`

- **conftest.py**: Create in-memory SQLite async engine, seed data, `httpx.AsyncClient` with FastAPI test app, helper to create auth headers
- **test_auth.py**:
  - Test `GET /rest/api/2/myself` returns user with Basic auth (username:password)
  - Test `GET /rest/api/2/myself` returns user with Bearer token (PAT)
  - Test `POST /rest/auth/1/session` returns session cookie on valid credentials
  - Test `GET /rest/auth/1/session` returns user info when session active
  - Test `DELETE /rest/auth/1/session` invalidates session
  - Test `PUT /rest/api/2/myself/password` changes own password
  - Test 401 response for invalid credentials (strict mode)
  - Test permissive mode accepts any auth header
  - Test none mode requires no auth
- **test_users.py**:
  - Test `POST /rest/api/2/user` creates user with password
  - Test `GET /rest/api/2/user?username=X` returns user details
  - Test `PUT /rest/api/2/user?username=X` updates email/displayName
  - Test `PUT /rest/api/2/user/password?username=X` admin changes another user's password
  - Test newly created user can authenticate with their password
- **test_tokens.py**:
  - Test `POST /rest/pat/latest/tokens` creates token and returns rawToken once
  - Test `GET /rest/pat/latest/tokens` lists tokens without raw values
  - Test `DELETE /rest/pat/latest/tokens/{id}` revokes token
  - Test revoked token returns 401
  - Test expired token returns 401
  - Test Bearer auth with valid PAT succeeds
- **test_issues.py**: Create issue → get issue → update issue → delete issue; validate all response field formats
- **test_search.py**: Create multiple issues → search with JQL (`project = X`, `status = Y`, `assignee = Z`, `summary ~ "text"`, `key = X-1`, AND/OR combinations, ORDER BY) → verify results
- **test_projects.py**: List projects, get project by key
- **test_metadata.py**: List priorities, statuses, resolutions, issue types, fields

**Phase 1 acceptance criteria:**
- `GET /rest/api/2/myself` returns valid user JSON when authenticated with Basic (username:password) or Bearer (PAT)
- `POST /rest/api/2/user` creates a user with hashed password; user can then authenticate
- `POST /rest/pat/latest/tokens` creates a PAT; Bearer auth with that PAT resolves to the owning user
- `POST /rest/auth/1/session` returns a session cookie for valid username:password
- Strict mode returns 401 for invalid credentials; permissive mode always succeeds
- `POST /rest/api/2/issue` creates issue with auto-generated key
- `GET /rest/api/2/issue/RHAIRFE-1` returns full issue JSON matching Jira format
- `PUT /rest/api/2/issue/RHAIRFE-1` updates fields
- `POST /rest/api/2/search` with `jql=project = RHAIRFE` returns matching issues
- `GET /rest/api/2/project` lists 4 seeded projects
- All metadata endpoints return seeded data
- Container builds and runs with `podman build && podman run -p 8080:8080`

---

## Phase 2: Full Feature Set

**Goal:** Workflow transitions, issue links, watchers, full JQL, update operations — all 24 `assistant_mcp` tools work.

### Step 2.1 — Workflow service

**Files:** `src/jira_emulator/services/workflow_service.py`

- `get_workflow_for_issue(db, issue)` → Workflow
  - Look up `project_workflows` for (project_id, issue_type_id)
  - Fall back to (project_id, NULL)
  - Fall back to "Default" workflow
- `get_available_transitions(db, issue)` → list[WorkflowTransition]
  - Query transitions where `from_status_id = issue.status_id` OR `from_status_id IS NULL` (global transitions)
  - Return transition id, name, target status
- `execute_transition(db, issue, transition_id)`:
  - Validate transition is available
  - Update issue status
  - If target status category is "done": auto-set resolution to "Done", set `resolved_at`
  - If source status category was "done" and target is not: clear resolution, clear `resolved_at`
  - Update `updated_at`
  - Raise 400 if transition not available

### Step 2.2 — Transition routers

**Files:** Update `src/jira_emulator/routers/issues.py`

- `GET /rest/api/2/issue/{issueIdOrKey}/transitions` → list available transitions
- `POST /rest/api/2/issue/{issueIdOrKey}/transitions` → execute transition (204)
  - Accept optional `fields` and `update` in request body (for comment-on-transition)

### Step 2.3 — Issue links

**Files:** `src/jira_emulator/routers/links.py`, update issue service

- `POST /rest/api/2/issueLink` → create link (201)
  - Validate both issues exist
  - Validate link type exists
- `GET /rest/api/2/issueLinkType` → list link types
- Update `format_issue_response()` to include `issuelinks` array:
  ```json
  {
    "id": "1",
    "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
    "inwardIssue": {"key": "...", "fields": {"summary": "...", "status": {...}}},
    "outwardIssue": {"key": "...", "fields": {"summary": "...", "status": {...}}}
  }
  ```

### Step 2.4 — Watchers

**Files:** Update `src/jira_emulator/routers/issues.py`

- `GET /rest/api/2/issue/{issueIdOrKey}/watchers` → return watchers list
  ```json
  {"self": "...", "isWatching": false, "watchCount": 2, "watchers": [...]}
  ```
- `POST /rest/api/2/issue/{issueIdOrKey}/watchers` → add watcher (body is JSON string: `"username"`)
- `DELETE /rest/api/2/issue/{issueIdOrKey}/watchers?username=X` → remove watcher (204)

### Step 2.5 — Update operations (SET/ADD/REMOVE)

**Files:** Update `src/jira_emulator/services/issue_service.py`

Extend `update_issue()` to handle the `update` dict format:

- `labels`: `[{"add": "new"}, {"remove": "old"}, {"set": ["a", "b"]}]`
- `components`: `[{"add": {"name": "X"}}, {"remove": {"name": "Y"}}]`
- `fixVersions`: `[{"add": {"name": "v1"}}, {"remove": {"name": "v2"}}]`
- `comment`: `[{"add": {"body": "text"}}]`
- Mixed `fields` + `update` in one request: process both, each field appears in only one

### Step 2.6 — Full JQL parser

**Files:** Update `src/jira_emulator/jql/grammar.py`, `transformer.py`, `functions.py`

Extend Phase 1 JQL to full spec:

- **Additional operators**: `>`, `>=`, `<`, `<=` (for dates and numbers)
- **Additional fields**:
  - `component` → EXISTS subquery on issue_components + components
  - `fixVersion` → EXISTS subquery on issue_fix_versions + versions
  - `affectedVersion` → EXISTS subquery on issue_affects_versions + versions
  - `resolution` → resolutions.name lookup
  - `due` / `duedate` → issues.due_date
  - `parent` → parent issue key
  - `text` → combined summary + description search
  - `comment` → EXISTS subquery on comments.body LIKE
  - `cf[NNNNN]` → custom field value lookup
  - `sprint` → EXISTS subquery on issue_sprints + sprints
  - `statusCategory` → statuses.category lookup
- **Functions**:
  - `now()` → current UTC datetime
  - `startOfDay(offset?)` → today 00:00:00 + optional offset
  - `endOfDay(offset?)` → today 23:59:59 + optional offset
  - `startOfWeek(offset?)` → Monday 00:00:00 + offset
  - `endOfWeek(offset?)` → Sunday 23:59:59 + offset
  - `startOfMonth(offset?)` → 1st 00:00:00 + offset
  - `endOfMonth(offset?)` → last day 23:59:59 + offset
  - `startOfYear(offset?)` → Jan 1 00:00:00 + offset
  - `endOfYear(offset?)` → Dec 31 23:59:59 + offset
  - Offset parsing: `-1d`, `2w`, `3M`, etc.

### Step 2.7 — Custom fields in responses

**Files:** Update `src/jira_emulator/services/issue_service.py`

- Include all registered custom fields in issue response:
  - `customfield_12310243` (Story Points) → value_number
  - `customfield_12313240` (Team) → value_string
  - `customfield_12313941` (Target Start) → value_date formatted
  - `customfield_12313942` (Target End) → value_date formatted
  - `customfield_12310170` (Affects Testing) → value_json parsed
  - `customfield_12319743` (Release Blocker) → value_string
  - `customfield_12316142` (Severity) → value_string
- Custom field setting via create/update: detect `customfield_*` keys in `fields` dict

### Step 2.8 — Field selection in search

**Files:** Update `src/jira_emulator/services/search_service.py`

- `fields=["summary", "status"]` → only return those fields in each issue
- `fields=["*all"]` → return everything
- `fields=["*navigable"]` → return standard navigable fields
- Default: return all fields

### Step 2.9 — Phase 2 tests

**Files:** `tests/test_transitions.py`, `tests/test_links.py`, `tests/test_watchers.py`, update `tests/test_issues.py`, update `tests/test_search.py`, `tests/test_jql_parser.py`

- **test_transitions.py**: Test each workflow (RHAIRFE, RHAISTRAT, Default), valid/invalid transitions, auto-resolution on done, clear resolution on reopen
- **test_links.py**: Create link, verify in issue response, list link types
- **test_watchers.py**: Add/remove/list watchers
- **test_issues.py**: Add tests for update operations (add/remove labels, components, comments via `update` dict)
- **test_search.py**: Add JQL tests for all new operators, functions, fields, ORDER BY with multiple columns
- **test_jql_parser.py**: Unit tests for each grammar rule, operator, function

**Phase 2 acceptance criteria:**
- `GET /rest/api/2/issue/{key}/transitions` returns valid transitions for current status
- `POST /rest/api/2/issue/{key}/transitions` changes status correctly
- Issue links appear in issue response `issuelinks` array
- Watchers CRUD works
- `PUT /rest/api/2/issue/{key}` with `update` dict handles add/remove verbs
- JQL with dates, functions, custom fields, all operators works
- All 24 `assistant_mcp` tool functions can execute against the emulator

---

## Phase 3: Import System

**Goal:** Import real Jira JSON exports, seed the emulator with production-like data.

### Step 3.1 — Import service

**Files:** `src/jira_emulator/services/import_service.py`

- `import_issue(db, issue_data: dict)` → ImportResult
  - Auto-create project from `issue_data["project"]`
  - Auto-create users from `assignee` / `reporter` (display_name → slugified username)
  - Auto-create issue type from `issue_type`
  - Auto-create status from `status` (default category: "indeterminate")
  - Auto-create priority from `priority`
  - Auto-create components from `components[]`
  - Auto-create versions from `fix_versions[]`, `affects_versions[]`, `target_versions[]`
  - Preserve original issue key
  - Map custom fields:
    - `team` → `customfield_12313240`
    - `story_points` → `customfield_12310243`
    - `target_start` → `customfield_12313941`
    - `target_end` → `customfield_12313942`
    - `affects_testing` → `customfield_12310170`
    - `release_blocker` → `customfield_12319743`
    - `severity` → `customfield_12316142`
  - Handle `epic_link`: create parent-child relationship (if parent exists; queue for second pass if not)
  - Handle `sprints[]`: auto-create sprint records, associate
  - Parse ISO 8601 timestamps for `created`/`updated`
  - Idempotent: if issue key exists, update all fields
- `import_file(db, path: str)` → ImportResult
  - Read JSON file
  - If it's a list, iterate and call `import_issue` for each
  - If it's a single object, call `import_issue` once
- `import_directory(db, dir_path: str)` → ImportResult
  - Scan for `*.json` files
  - Import each file
  - Two-pass: first pass creates all issues, second pass resolves epic_links/parent references
  - Update `issue_sequences` to max(number) + 1 for each project
- Aggregate results: total imported, total updated, errors list, projects_created, users_created

### Step 3.2 — CLI import command

**Files:** Update `src/jira_emulator/__main__.py`

- `python -m jira_emulator import <path>`:
  - If path is a file: call `import_file()`
  - If path is a directory: call `import_directory()`
  - Print summary (imported/updated/errors)
  - Use synchronous wrapper around async import

### Step 3.3 — Admin API import endpoint

**Files:** `src/jira_emulator/routers/admin.py`

- `POST /api/admin/import` → accept JSON body with `issues` array
  - Call `import_issue()` for each
  - Return ImportResponse

### Step 3.4 — Startup import

**Files:** Update `src/jira_emulator/app.py`

- In startup event, after seed data:
  - If `IMPORT_ON_STARTUP=true` and `IMPORT_DIR` exists and has `.json` files:
    - Call `import_directory(IMPORT_DIR)`
    - Log results

### Step 3.5 — Phase 3 tests

**Files:** `tests/test_import.py`

- Test single issue import with all fields
- Test bulk import (list of issues)
- Test directory import
- Test auto-creation of projects, users, issue types, statuses
- Test idempotent re-import (update existing issue)
- Test epic_link resolution (parent created after child)
- Test issue sequence update after import
- Test custom field mapping
- Create sample test fixture JSON files in `tests/fixtures/`

**Phase 3 acceptance criteria:**
- `python -m jira_emulator import /path/to/issues/` imports all JSON files
- Auto-created entities (projects, users, etc.) appear in API responses
- Imported issues searchable via JQL
- Re-import updates existing issues without duplicates
- `POST /api/admin/import` works via HTTP
- Startup import works with `IMPORT_ON_STARTUP=true`

---

## Phase 4: Web UI + Polish

**Goal:** Browsable web interface, production-ready container, documentation.

### Step 4.1 — Template setup

**Files:** `src/jira_emulator/web/routes.py`, `src/jira_emulator/web/templates/base.html`

- Configure Jinja2 template directory in FastAPI app
- Create `base.html` with:
  - Pico CSS via CDN (`<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">`)
  - Navigation bar: Home, Issues, Projects, Admin
  - Footer with version
- Mount static files directory

### Step 4.2 — Home page

**Files:** `src/jira_emulator/web/templates/home.html`

- `GET /` → render home.html
- Content:
  - Project list table (key, name, issue count) with links to `/project/{key}`
  - System stats: total issues, total users, DB file size
  - Last import info (if any imports have been run)

### Step 4.3 — Project view

**Files:** `src/jira_emulator/web/templates/project.html`

- `GET /project/{key}` → render project.html
- Content:
  - Project name, key, description, lead
  - Issue type breakdown (counts per type)
  - Status breakdown (counts per status)
  - Link to issues filtered by project: `/issues?project={key}`

### Step 4.4 — Issue list

**Files:** `src/jira_emulator/web/templates/issues.html`

- `GET /issues` → render issues.html
- Query params: `project`, `status`, `q` (text search), `page`
- Content:
  - Filter controls: project dropdown, status dropdown, text search input
  - Paginated table: Key (linked), Summary, Status, Priority, Assignee, Type, Created
  - Sort by clicking column headers
  - Pagination controls (prev/next)
- Build JQL from filter params, use search_service internally

### Step 4.5 — Issue detail

**Files:** `src/jira_emulator/web/templates/issue_detail.html`

- `GET /issue/{key}` → render issue_detail.html
- Content:
  - Header: key + summary
  - Two-column layout:
    - Left: description (plain text), comments list
    - Right: status, priority, type, assignee, reporter, created, updated, resolution, due date, labels, components, fix versions, custom fields
  - Linked issues section
  - Watchers list

### Step 4.6 — Admin import page

**Files:** `src/jira_emulator/web/templates/admin_import.html`

- `GET /admin/import` → render form
- `POST /admin/import` → handle file upload
  - Accept `.json` file upload
  - Parse and import
  - Display results on same page

### Step 4.7 — Error handling polish

**Files:** Update `src/jira_emulator/app.py`

- Custom exception classes: `IssueNotFoundError`, `ProjectNotFoundError`, `InvalidTransitionError`, `JQLParseError`
- Exception handlers that return Jira-format error JSON with correct HTTP status codes
- Consistent logging of all API requests (method, path, status, duration)

### Step 4.8 — Logging

**Files:** Update `src/jira_emulator/app.py`, `src/jira_emulator/config.py`

- Configure Python logging with `LOG_LEVEL` from config
- Request/response logging middleware (path, method, status, ms)
- Import progress logging (every N issues)

### Step 4.9 — Phase 4 tests

**Files:** `tests/test_client_compat.py`

- Integration tests that mirror the exact call patterns from `assistant_mcp`:
  - Auth check → search → get issue → create issue → update → transition → comment → link → watcher → delete
  - Verify response JSON structure matches what the client expects
  - Test field selection in search results
  - Test JQL patterns actually used by the tools

### Step 4.10 — Container finalization

**Files:** Update `Dockerfile`, create `.dockerignore`

- `.dockerignore`: exclude `.git`, `tests/`, `__pycache__`, `*.pyc`, `.claude/`
- Multi-stage build if needed for smaller image
- Health check: `HEALTHCHECK CMD python -c "import httpx; httpx.get('http://localhost:8080/rest/api/2/myself')"`
- Verify build + run works with podman and docker

---

## Implementation Order Summary

| # | Step | Key Deliverable |
|---|------|----------------|
| 1 | 1.1 | `pyproject.toml`, `requirements.txt` (incl. bcrypt) |
| 2 | 1.2 | `config.py` — settings from env |
| 3 | 1.3 | `database.py` — async SQLAlchemy setup |
| 4 | 1.4 | `models/*.py` — all 18 ORM model files (incl. ApiToken) |
| 5 | 1.5 | `seed_service.py` + `seed.yaml` — reference data + admin user w/ password |
| 6 | 1.6 | `auth_service.py` + `auth/middleware.py` — password hashing, token generation, Basic/Bearer/session auth |
| 7 | 1.7 | `schemas/*.py` — Pydantic models (incl. auth schemas) |
| 8 | 1.8 | `user_service.py` — user CRUD with password support |
| 9 | 1.9 | `issue_service.py` — issue CRUD + response formatting |
| 10 | 1.10 | `project_service.py` — project queries |
| 11 | 1.11 | `jql/` — grammar + parser + transformer (basic) |
| 12 | 1.12 | `search_service.py` — JQL search orchestration |
| 13 | 1.13 | `routers/*.py` — all Phase 1 API endpoints (incl. auth, users, tokens) |
| 14 | 1.14 | `app.py` — FastAPI app factory + startup |
| 15 | 1.15 | `__main__.py` — CLI entry point |
| 16 | 1.16 | `Dockerfile` |
| 17 | 1.17 | Phase 1 tests (incl. auth, users, tokens) |
| 18 | 2.1 | `workflow_service.py` — transition engine |
| 19 | 2.2 | Transition endpoints |
| 20 | 2.3 | Issue link endpoints + response formatting |
| 21 | 2.4 | Watcher endpoints |
| 22 | 2.5 | Update operations (add/remove/set verbs) |
| 23 | 2.6 | Full JQL parser (all operators, functions, fields) |
| 24 | 2.7 | Custom fields in responses |
| 25 | 2.8 | Field selection in search |
| 26 | 2.9 | Phase 2 tests |
| 27 | 3.1 | `import_service.py` — JSON import engine |
| 28 | 3.2 | CLI import command |
| 29 | 3.3 | Admin API import endpoint |
| 30 | 3.4 | Startup import |
| 31 | 3.5 | Phase 3 tests |
| 32 | 4.1 | Jinja2 + Pico CSS template base |
| 33 | 4.2 | Home page |
| 34 | 4.3 | Project view page |
| 35 | 4.4 | Issue list page |
| 36 | 4.5 | Issue detail page |
| 37 | 4.6 | Admin import page |
| 38 | 4.7 | Error handling polish |
| 39 | 4.8 | Logging |
| 40 | 4.9 | Client compatibility tests |
| 41 | 4.10 | Container finalization |

---

## Key Design Decisions

1. **Async throughout**: Use `async def` for all route handlers, service methods, and DB queries. SQLite is fast enough that async overhead is negligible, and it matches FastAPI best practices.

2. **Service layer pattern**: Routers are thin (validation + HTTP concerns), services contain business logic, models are pure data. This keeps routers testable and logic reusable between API and import.

3. **JQL as SQL translation**: Rather than loading all issues into Python and filtering, translate JQL directly to SQL WHERE clauses for performance. This is the most complex piece and should be well-tested.

4. **Auto-entity creation**: Both the import system and the API create-issue endpoint auto-create users, components, etc. This keeps the emulator low-friction — you don't need to set up all reference data before creating issues.

5. **Response format fidelity**: The exact JSON structure matters more than data accuracy. The `assistant_mcp` client parses specific field paths (e.g., `issue["fields"]["status"]["name"]`), so the response shape must match Jira's API exactly.

6. **Issue key preservation on import**: Imported issues keep their original keys. The sequence counter is adjusted to avoid collisions with future creates. This is critical for testing with real data.

7. **Single `models/__init__.py` import**: All models must be imported before `Base.metadata.create_all()` runs, so `models/__init__.py` imports every model class to register them.

---

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| JQL grammar edge cases (quotes, escapes, special chars) | Extensive unit tests for parser; reference the lark grammar against real JQL from client logs |
| SQLAlchemy async + SQLite concurrency | Use WAL mode; keep transactions short; single-writer pattern is fine for emulator scale |
| Custom field type handling complexity | Keep it simple: store everything as string/number/json; don't implement full Jira field type system |
| Response format mismatches with real Jira | Compare emulator responses against saved real Jira API responses from `mcp_session_data/` |
| Import of large datasets (1000+ issues) | Batch commits (every 100 issues); progress logging; tested in Phase 3 perf tests |
