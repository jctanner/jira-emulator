# Jira REST API v2 - Endpoint Reference

Collected from Atlassian developer documentation, March 2026.

## Sources

- https://developer.atlassian.com/cloud/jira/platform/rest/v2/intro/
- https://developer.atlassian.com/server/jira/platform/jira-rest-api-examples/
- https://docs.atlassian.com/software/jira/docs/api/REST/1000.824.0/
- https://developer.atlassian.com/server/jira/platform/updating-an-issue-via-the-jira-rest-apis-6848604/

## Key Concepts

- Base URL: `{host}/rest/api/2/`
- Authentication: Basic Auth (Cloud: email + API token) or Bearer Token (Server/DC: PAT)
- Pagination: `startAt` (0-indexed), `maxResults` (default 50, max varies)
- Resource expansion: `?expand=transitions.fields` to include nested data
- Custom fields: referenced as `customfield_{id}` (e.g., `customfield_10000`)
- Success responses: 201 for creation, 204 for updates, 200 for reads
- v2 vs v3: Same endpoints, v3 adds Atlassian Document Format (ADF) support

## Endpoints Required for Emulator

### Issues

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rest/api/2/issue` | Create issue |
| GET | `/rest/api/2/issue/{issueIdOrKey}` | Get issue |
| PUT | `/rest/api/2/issue/{issueIdOrKey}` | Update issue |
| DELETE | `/rest/api/2/issue/{issueIdOrKey}` | Delete issue |
| GET | `/rest/api/2/issue/{issueIdOrKey}/transitions` | Get available transitions |
| POST | `/rest/api/2/issue/{issueIdOrKey}/transitions` | Transition issue |
| GET | `/rest/api/2/issue/{issueIdOrKey}/comment` | Get comments |
| POST | `/rest/api/2/issue/{issueIdOrKey}/comment` | Add comment |
| GET | `/rest/api/2/issue/{issueIdOrKey}/editmeta` | Get editable fields metadata |
| GET | `/rest/api/2/issue/{issueIdOrKey}/watchers` | Get watchers |
| POST | `/rest/api/2/issue/{issueIdOrKey}/watchers` | Add watcher |
| DELETE | `/rest/api/2/issue/{issueIdOrKey}/watchers?username={username}` | Remove watcher |
| GET | `/rest/api/2/issue/createmeta` | Get create issue metadata |
| GET | `/rest/api/2/issue/createmeta/{projectIdOrKey}/issuetypes` | Get issue types for project |

### Search

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/search?jql=...` | Search issues via JQL (GET) |
| POST | `/rest/api/2/search` | Search issues via JQL (POST) |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/project` | List all projects |
| GET | `/rest/api/2/project/{projectIdOrKey}` | Get project |

### Fields

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/field` | List all fields (system + custom) |

### Issue Links

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rest/api/2/issueLink` | Create issue link |
| GET | `/rest/api/2/issueLinkType` | Get link types |

### Users

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/myself` | Get current user (auth check) |
| GET | `/rest/api/2/user?username={username}` | Get user |
| GET | `/rest/api/2/user/assignable/search?project={key}` | Get assignable users |

### Priorities, Statuses, Resolutions, Issue Types

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/priority` | List priorities |
| GET | `/rest/api/2/status` | List statuses |
| GET | `/rest/api/2/resolution` | List resolutions |
| GET | `/rest/api/2/issuetype` | List issue types |

### Components

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/project/{key}/components` | Get project components |
| POST | `/rest/api/2/component` | Create component |

### Versions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/project/{key}/versions` | Get project versions |
| POST | `/rest/api/2/version` | Create version |

## JSON Schemas

### Create Issue Request

```json
{
  "fields": {
    "project": {"key": "TEST"},
    "summary": "Issue summary",
    "description": "Issue description",
    "issuetype": {"name": "Bug"},
    "priority": {"name": "Major"},
    "assignee": {"name": "charlie"},
    "labels": ["label1", "label2"],
    "components": [{"name": "Engine"}],
    "fixVersions": [{"name": "1.0"}],
    "customfield_10000": "custom value"
  }
}
```

### Create Issue Response

```json
{
  "id": "39000",
  "key": "TEST-101",
  "self": "http://localhost:8080/rest/api/2/issue/39000"
}
```

### Get Issue Response (abbreviated)

```json
{
  "expand": "renderedFields,names,schema,operations,editmeta,changelog,versionedRepresentations",
  "id": "10230",
  "self": "http://localhost:8080/rest/api/2/issue/10230",
  "key": "PROJ-123",
  "fields": {
    "summary": "Issue summary",
    "description": "Issue description",
    "status": {"name": "Open", "id": "1"},
    "priority": {"name": "Major", "id": "3"},
    "issuetype": {"name": "Bug", "id": "1", "subtask": false},
    "assignee": {"displayName": "Charlie", "name": "charlie", "accountId": "..."},
    "reporter": {"displayName": "Alice", "name": "alice", "accountId": "..."},
    "project": {"key": "PROJ", "name": "Project Name", "id": "10000"},
    "created": "2026-01-15T10:30:00.000+0000",
    "updated": "2026-03-20T14:22:00.000+0000",
    "resolution": null,
    "labels": ["label1"],
    "components": [{"name": "Engine", "id": "10001"}],
    "fixVersions": [{"name": "1.0", "id": "10100"}],
    "comment": {
      "comments": [
        {
          "id": "10001",
          "author": {"displayName": "Alice", "name": "alice"},
          "body": "Comment text",
          "created": "2026-01-16T09:00:00.000+0000"
        }
      ],
      "total": 1
    },
    "customfield_10000": "value"
  }
}
```

### Update Issue Request

Two styles supported:

**Style 1: Fields object**
```json
{
  "fields": {
    "summary": "Updated summary",
    "assignee": {"name": "charlie"}
  }
}
```

**Style 2: Update operations**
```json
{
  "update": {
    "components": [{"add": {"name": "Engine"}}],
    "labels": [{"add": "new-label"}, {"remove": "old-label"}],
    "comment": [{"add": {"body": "A comment"}}]
  }
}
```

### Search Request (POST)

```json
{
  "jql": "project = TEST AND status = Open",
  "startAt": 0,
  "maxResults": 50,
  "fields": ["id", "key", "summary", "status", "assignee"]
}
```

### Search Response

```json
{
  "expand": "schema,names",
  "startAt": 0,
  "maxResults": 50,
  "total": 6,
  "issues": [
    {
      "expand": "html",
      "id": "10230",
      "self": "http://localhost:8080/rest/api/2/issue/10230",
      "key": "PROJ-123",
      "fields": {
        "summary": "Issue summary",
        "status": {"name": "Open"},
        "assignee": {"displayName": "Charlie"}
      }
    }
  ]
}
```

### Transition Request

```json
{
  "transition": {"id": "5"},
  "fields": {},
  "update": {
    "comment": [{"add": {"body": "Transitioning to In Progress"}}]
  }
}
```

### Comment Request

```json
{
  "body": "This is a comment."
}
```

### Issue Link Request

```json
{
  "type": {"name": "Blocks"},
  "inwardIssue": {"key": "PROJ-123"},
  "outwardIssue": {"key": "PROJ-456"}
}
```
