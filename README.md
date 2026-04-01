# Jira Emulator

A lightweight Jira REST API v2 emulator for offline development and testing. Runs entirely on SQLite — no external services required.

Built for use with tools like [jira-python](https://github.com/pycontribs/jira) and other Jira API clients that need a local target for integration testing, CI pipelines, or offline development.

## Features

- **REST API v2** — Issues, projects, search, comments, transitions, watchers, issue links, users, fields, and metadata endpoints
- **JQL Search** — Lark-based parser supporting `AND`/`OR`, `IN`, `NOT IN`, `IS EMPTY`, `~` text search, `ORDER BY`, date functions (`now()`, `startOfDay()`, etc.), custom fields, and `statusCategory`
- **Workflow Engine** — Configurable workflows with status transitions, auto-resolution on done, and per-project/issue-type mapping
- **Authentication** — Three modes: `permissive` (default, accepts anything), `strict` (validates passwords and tokens), `none` (no auth required). Supports Basic auth, Bearer tokens (PATs), and session cookies.
- **JSON Import** — Import real Jira JSON exports via CLI, HTTP API, or file upload. Auto-creates projects, users, statuses, and other entities on the fly.
- **Web UI** — Browse projects, issues, and run JQL queries from your browser. Built with Pico CSS.
- **Container Ready** — Dockerfile included. `make run` builds and starts a container.

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
make run PORT=9090

# View logs
make logs

# Stop and remove
make stop
```

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

# Search with JQL
curl -u admin:admin -X POST http://localhost:8080/rest/api/2/search \
  -H 'Content-Type: application/json' \
  -d '{"jql": "project = RHAIRFE ORDER BY created DESC"}'

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

## API Coverage

### Endpoints

| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/rest/api/2/issue` | POST | Create issue |
| `/rest/api/2/issue/{id}` | GET, PUT, DELETE | Issue CRUD |
| `/rest/api/2/issue/{id}/comment` | GET, POST | Comments |
| `/rest/api/2/issue/{id}/transitions` | GET, POST | Workflow transitions |
| `/rest/api/2/issue/{id}/watchers` | GET, POST, DELETE | Watchers |
| `/rest/api/2/search` | GET, POST | JQL search |
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

### JQL Support

Operators: `=`, `!=`, `~`, `!~`, `IN`, `NOT IN`, `IS EMPTY`, `IS NOT EMPTY`, `>`, `>=`, `<`, `<=`

Fields: `project`, `status`, `statusCategory`, `assignee`, `reporter`, `priority`, `issuetype`, `summary`, `description`, `text`, `key`, `labels`, `component`, `fixVersion`, `affectedVersion`, `resolution`, `due`, `created`, `updated`, `parent`, `comment`, `sprint`, `cf[NNNNN]`, `customfield_*`

Functions: `currentUser()`, `now()`, `startOfDay()`, `endOfDay()`, `startOfWeek()`, `endOfWeek()`, `startOfMonth()`, `endOfMonth()`, `startOfYear()`, `endOfYear()`

## Project Structure

```
src/jira_emulator/
├── app.py              # FastAPI application factory
├── config.py           # Environment-based configuration
├── database.py         # Async SQLAlchemy engine + sessions
├── exceptions.py       # Custom exception hierarchy
├── auth/               # Authentication middleware
├── jql/                # JQL parser (Lark grammar + transformer)
├── models/             # SQLAlchemy ORM models (18 models)
├── routers/            # FastAPI route handlers
├── schemas/            # Pydantic request/response models
├── services/           # Business logic layer
└── web/                # Web UI (Jinja2 templates)
```

## License

MIT
