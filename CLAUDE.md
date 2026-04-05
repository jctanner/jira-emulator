# CLAUDE.md — Jira Emulator

## What is this?

A lightweight Jira REST API emulator built with Python/FastAPI and SQLite. Designed for offline development, testing, CI/CD integration, and Claude AI integration via MCP. It provides feature parity with real Jira for common operations (issues, JQL search, workflows, auth, attachments).

**We must support and test three API surfaces: REST API v2, REST API v3, and the MCP service.** All three are first-class interfaces and must have test coverage. Any new feature or endpoint must work across v2 and v3, and corresponding MCP tools must be updated when applicable.

## Tech Stack

- **Python 3.11+**, **FastAPI**, **Uvicorn** (async web framework)
- **SQLAlchemy 2.0+** with asyncio + **aiosqlite** (async SQLite ORM)
- **Pydantic 2.5+** (request/response validation)
- **Lark** (JQL parser with context-free grammar)
- **Jinja2** (web UI templates, Pico CSS)
- **bcrypt** (password hashing)
- **FastMCP** (Model Context Protocol server for Claude integration)
- **Docker/Podman** + **supervisord** (containerization)

## Common Commands

**Always use the Makefile targets** — they handle `uv run`, correct env vars, and container orchestration. Do not invoke `pytest`, `uvicorn`, or container commands directly.

```bash
make test           # Run pytest suite: uv run pytest tests/ -x -q
make serve          # Start dev server with auto-reload (port 8080)
make serve-mcp      # Start MCP server (port 8081)
make serve-all      # Start both API and MCP servers
make run            # Build and run container (podman, port 8080)
make stop           # Stop container
make restart        # Stop + run
make logs           # Follow container logs
make status         # Show container status
make clean          # Remove container, image, and data volume
```

## Project Layout

```
src/jira_emulator/
  app.py              # FastAPI app factory, lifespan, exception handlers
  config.py           # Environment-based settings (pydantic)
  database.py         # SQLAlchemy engine/session factory
  __main__.py         # CLI entry point (serve, import)
  adf.py              # Atlassian Document Format serialization
  exceptions.py       # Custom exception hierarchy
  auth/middleware.py   # Auth middleware, get_current_user dependency
  jql/                # JQL search engine (Lark grammar, parser, transformer, functions)
  models/             # SQLAlchemy ORM models (~21 tables)
  routers/            # FastAPI route handlers (issues, search, projects, auth, etc.)
  services/           # Business logic layer (issue, search, import, auth, workflow, etc.)
  schemas/            # Pydantic request/response models
  web/                # Web UI (Jinja2 templates + routes)
tests/                # pytest test suite (~18 test files, ~110 test cases)
  conftest.py         # Fixtures: fresh in-memory SQLite DB per test, seed data
  fixtures/           # Test data (JSON import examples)
mcp_servers/          # FastMCP server for Claude integration (7 tools)
references/           # Jira API specs, JQL spec, auth spec, workflow research
```

## Architecture

- **Service layer pattern**: Routers handle HTTP concerns; services encapsulate business logic; models define schema; schemas define API contracts.
- **Async-first**: asyncio throughout (FastAPI, SQLAlchemy AsyncSession, httpx).
- **Dependency injection**: FastAPI `Depends()` for auth (`get_current_user`), DB sessions (`get_db`), config.
- **Error responses** follow Jira format: `{"errorMessages": ["..."], "errors": {...}}`

## Testing

- **pytest + pytest-asyncio** with `httpx.AsyncClient`
- Each test gets a fresh in-memory SQLite database (via `conftest.py` fixtures)
- Auth header in tests: Base64-encoded `admin:admin`
- Run a single test: `pytest tests/test_issues.py::test_create_issue -x -v`
- **All three API surfaces must be tested**: REST API v2 (`/rest/api/2/...`), REST API v3 (`/rest/api/3/...`), and MCP tools. When adding or modifying functionality, ensure test coverage exists for each surface.

## Key Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `AUTH_MODE` | `permissive` | `permissive` / `strict` / `none` |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/jira.db` | Database connection |
| `PORT` | `8080` | Server port |
| `SEED_DATA` | `true` | Auto-load sample projects/workflows |
| `IMPORT_ON_STARTUP` | `false` | Auto-import JSON on startup |
| `ATTACHMENT_DIR` | `/data/attachments` | File upload storage |

## Database Snapshots (Containerized Mode)

The emulator supports database backup and restore via the admin API, useful for test isolation and data recovery:

- `POST /api/admin/snapshots` — Create a snapshot of the current database
- `GET /api/admin/snapshots` — List available snapshots
- `POST /api/admin/snapshots/{id}/restore` — Restore database from a snapshot

Snapshots are stored in the persistent `/data` volume when running in a container.

## Conventions

- **DateTime format**: ISO 8601 with milliseconds: `2026-04-02T14:47:28.592+0000`
- **Issue keys**: Per-project auto-incrementing sequence (e.g., `RHAIRFE-1`, `RHAIRFE-2`)
- **API versioning**: Both v2 and v3 are first-class. v3 requests are rewritten to v2 endpoints internally via middleware (`app.py`), with `request.state.api_version` used to branch response format where they differ (e.g., pagination, ADF). Both must be tested independently.
- **Pagination**: v2 uses `startAt` (0-indexed) + `maxResults` (default 50). v3 uses `nextPageToken` (opaque base64 cursor) + `maxResults` + `isLast`. The v3 response omits `startAt` and includes `nextPageToken` only when more results exist.
- **Search endpoints**: All combinations are implemented:
  - v2: `GET /search`, `POST /search`, `GET /search/jql`, `POST /search/jql` — offset pagination
  - v3: same paths via `/rest/api/3/` — cursor pagination (`nextPageToken`/`isLast`)
- **Seed projects**: RHOAIENG, RHAIRFE, RHAISTRAT, TEST with standard workflows

## References

The `references/` directory contains Jira API specifications used to build this emulator:
- REST API v2 endpoint catalog
- JQL operators, fields, and functions
- Authentication methods (Basic, Bearer/PAT, Cookie)
- Attachment upload/download specs
- Workflow and status customization
- API v2 to v3 migration notes
