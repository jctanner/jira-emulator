# Jira Emulator

A lightweight Jira REST API emulator supporting both **v2** (Server/DC) and **v3** (Cloud) for offline development and testing. Runs entirely on SQLite — no external services required.

Built for use with tools like [jira-python](https://github.com/pycontribs/jira) and other Jira API clients that need a local target for integration testing, CI pipelines, or offline development. Also includes an MCP (Model Context Protocol) server for Claude AI integration.

## Features

- **REST API v2 + v3** — Issues, projects, search, comments, transitions, watchers, issue links, attachments, users, fields, and metadata endpoints. v3 requests are supported with proper ADF formatting and cursor-based pagination.
- **JQL Search** — Lark-based parser supporting `AND`/`OR`, `IN`, `NOT IN`, `IS EMPTY`, `~` text search, `ORDER BY`, date functions (`now()`, `startOfDay()`, etc.), custom fields, and `statusCategory`
- **Workflow Engine** — Configurable workflows with status transitions, auto-resolution on done, reopen transitions, and per-project/issue-type mapping
- **Authentication** — Three modes: `permissive` (default, accepts anything), `strict` (validates passwords and tokens), `none` (no auth required). Supports Basic auth, Bearer tokens (PATs), and session cookies.
- **File Attachments** — Upload, download, and delete file attachments on issues. Supports `X-Atlassian-Token: no-check` header.
- **JSON Import** — Import real Jira JSON exports via CLI, HTTP API, or file upload. Auto-creates projects, users, statuses, and other entities on the fly.
- **Database Snapshots** — Backup and restore database state via the admin API. Useful for test isolation.
- **MCP Server** — Model Context Protocol server for Claude AI integration with tools for searching, creating, updating, and transitioning issues.
- **Web UI** — Browse projects, issues, and run JQL queries from your browser. Built with Pico CSS.
- **Container Ready** — Dockerfile included. `make run` builds and starts a container with persistent storage.

## Quick Start

### Run locally

```bash
# Install dependencies
uv sync

# Start the server (auto-reload for development)
make serve

# Or without make:
uv run python -m jira_emulator serve --port 8080 --reload
```

### Run in a container

```bash
# Build and run (defaults to podman, port 8080)
make run

# Use docker instead
make run CONTAINER_ENGINE=docker

# Use a different port
make run JIRA_EMU_PORT=9090

# View logs
make logs

# Stop and remove
make stop
```

### Run with MCP server

```bash
# Start both API and MCP servers
make serve-all

# Or start the MCP server separately (requires API server running)
make serve-mcp
```

The MCP server runs on port 8081 and provides Claude AI with tools for issue search, creation, updates, and transitions.

### Run tests

```bash
make test
```

## Usage

The server starts with seed data including 4 projects, standard issue types, statuses, priorities, workflows, and an admin user.

### API Examples

```bash
# List projects
curl -u admin:admin http://localhost:8080/rest/api/2/project

# Create an issue
curl -u admin:admin -X POST http://localhost:8080/rest/api/2/issue \
  -H 'Content-Type: application/json' \
  -d '{
    "fields": {
      "project": {"key": "RHAIRFE"},
      "summary": "My first issue",
      "issuetype": {"name": "Bug"}
    }
  }'

# Search with JQL (v2 — offset pagination)
curl -u admin:admin -X POST http://localhost:8080/rest/api/2/search \
  -H 'Content-Type: application/json' \
  -d '{"jql": "project = RHAIRFE ORDER BY created DESC"}'

# Search with JQL (v3 — cursor pagination with nextPageToken)
curl -u admin:admin -X POST http://localhost:8080/rest/api/3/search/jql \
  -H 'Content-Type: application/json' \
  -d '{"jql": "project = RHAIRFE", "maxResults": 10}'

# Get an issue
curl -u admin:admin http://localhost:8080/rest/api/2/issue/RHAIRFE-1
```

### Web UI

Open [http://localhost:8080](http://localhost:8080) in your browser to access the web interface. No authentication required for the web UI.

- `/` — Dashboard with project list and stats
- `/issues` — Searchable, filterable issue list with JQL support
- `/issue/{key}` — Issue detail view
- `/project/{key}` — Project detail with status/type breakdowns
- `/admin/import` — Upload JSON files to import issues

### Importing Data

Import Jira JSON exports to populate the emulator with real data:

```bash
# Import a single file
uv run python -m jira_emulator import path/to/issues.json

# Import a directory of JSON files
uv run python -m jira_emulator import path/to/issues/

# Import on container startup
docker run -v ./my-issues:/data/import \
  -e IMPORT_ON_STARTUP=true \
  -p 8080:8080 jira-emulator
```

The import format is a JSON array (or single object) with fields like:

```json
{
  "key": "PROJ-123",
  "summary": "Fix the login page",
  "project": "PROJ",
  "status": "In Progress",
  "priority": "High",
  "issue_type": "Bug",
  "assignee": "Jane Smith",
  "reporter": "John Doe",
  "description": "The login page has a bug...",
  "labels": ["frontend", "auth"],
  "components": [{"name": "UI"}],
  "created": "2026-01-15T10:30:00.000+0000",
  "updated": "2026-01-16T14:00:00.000+0000"
}
```

Projects, users, statuses, priorities, and other entities are auto-created during import.

## Configuration

All settings are configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///data/jira.db` | SQLAlchemy database URL |
| `HOST` | `0.0.0.0` | Listen address |
| `PORT` | `8080` | Listen port |
| `AUTH_MODE` | `permissive` | Auth mode: `permissive`, `strict`, or `none` |
| `BASE_URL` | `http://localhost:8080` | Base URL for self-links in responses |
| `SEED_DATA` | `true` | Load seed data on first run |
| `ADMIN_PASSWORD` | `admin` | Password for the default admin user |
| `DEFAULT_USER` | `admin` | Default username when no auth is provided |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `IMPORT_ON_STARTUP` | `false` | Import JSON files from `IMPORT_DIR` on startup |
| `IMPORT_DIR` | `/data/import` | Directory to scan for JSON imports |
| `ATTACHMENT_DIR` | `/data/attachments` | Directory for uploaded file attachments |

## API Coverage

All endpoints below are available under both `/rest/api/2/` and `/rest/api/3/`. The v3 variants use ADF for rich-text fields and cursor-based pagination (`nextPageToken`) for search.

### Endpoints

| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/rest/api/2/issue` | POST | Create issue |
| `/rest/api/2/issue/{id}` | GET, PUT, DELETE | Issue CRUD |
| `/rest/api/2/issue/{id}/comment` | GET, POST | Comments |
| `/rest/api/2/issue/{id}/transitions` | GET, POST | Workflow transitions |
| `/rest/api/2/issue/{id}/watchers` | GET, POST, DELETE | Watchers |
| `/rest/api/2/issue/{id}/attachments` | POST | Upload attachments |
| `/rest/api/2/issue/createmeta` | GET | Issue creation metadata |
| `/rest/api/2/attachment/{id}` | GET, DELETE | Attachment metadata / delete |
| `/rest/api/2/attachment/content/{id}` | GET | Download attachment |
| `/rest/api/2/attachment/meta` | GET | Attachment settings |
| `/rest/api/2/search` | GET, POST | JQL search (v2: offset pagination) |
| `/rest/api/2/search/jql` | GET, POST | JQL search (v3: cursor pagination) |
| `/rest/api/2/project` | GET | List projects |
| `/rest/api/2/project/{id}` | GET | Get project |
| `/rest/api/2/field` | GET | List fields |
| `/rest/api/2/priority` | GET | List priorities |
| `/rest/api/2/status` | GET | List statuses |
| `/rest/api/2/resolution` | GET | List resolutions |
| `/rest/api/2/issuetype` | GET | List issue types |
| `/rest/api/2/issueLink` | POST | Create issue link |
| `/rest/api/2/issueLink/{id}` | DELETE | Delete issue link |
| `/rest/api/2/issueLinkType` | GET | List link types |
| `/rest/api/2/user` | POST, GET, PUT | User management |
| `/rest/api/2/user/password` | PUT | Change password |
| `/rest/api/2/user/assignable/search` | GET | Search assignable users |
| `/rest/api/2/myself` | GET | Current user |
| `/rest/api/2/myself/password` | PUT | Change own password |
| `/rest/auth/1/session` | POST, GET, DELETE | Session auth |
| `/rest/pat/latest/tokens` | POST, GET | PAT management |
| `/rest/pat/latest/tokens/{id}` | DELETE | Revoke PAT |
| `/api/admin/import` | POST | Bulk import |
| `/api/admin/snapshots` | GET, POST | List / create database snapshots |
| `/api/admin/snapshots/{id}/restore` | POST | Restore database snapshot |

### JQL Support

Operators: `=`, `!=`, `~`, `!~`, `IN`, `NOT IN`, `IS EMPTY`, `IS NOT EMPTY`, `>`, `>=`, `<`, `<=`

Fields: `project`, `status`, `statusCategory`, `assignee`, `reporter`, `priority`, `issuetype`, `summary`, `description`, `text`, `key`, `labels`, `component`, `fixVersion`, `affectedVersion`, `resolution`, `due`, `created`, `updated`, `parent`, `comment`, `sprint`, `cf[NNNNN]`, `customfield_*`

Functions: `currentUser()`, `now()`, `startOfDay()`, `endOfDay()`, `startOfWeek()`, `endOfWeek()`, `startOfMonth()`, `endOfMonth()`, `startOfYear()`, `endOfYear()`

## Project Structure

```
src/jira_emulator/
├── app.py              # FastAPI application factory, v3 rewrite middleware
├── config.py           # Environment-based configuration
├── database.py         # Async SQLAlchemy engine + sessions
├── adf.py              # Atlassian Document Format serialization
├── exceptions.py       # Custom exception hierarchy
├── auth/               # Authentication middleware
├── jql/                # JQL parser (Lark grammar + transformer)
├── models/             # SQLAlchemy ORM models (~21 tables)
├── routers/            # FastAPI route handlers
├── schemas/            # Pydantic request/response models
├── services/           # Business logic layer
└── web/                # Web UI (Jinja2 templates)

mcp_servers/
└── atlassian_jira.py   # FastMCP server for Claude AI integration

tests/                  # pytest test suite (~135 tests)
```

## License

MIT
