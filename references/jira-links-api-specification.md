# Jira REST API — Links Specification

Collected from Atlassian developer documentation, May 2026.

## Sources

- https://developer.atlassian.com/cloud/jira/platform/rest/v2/api-group-issue-links/
- https://developer.atlassian.com/cloud/jira/platform/rest/v2/api-group-issue-link-types/
- https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-remote-links/
- https://developer.atlassian.com/server/jira/platform/jira-rest-api-for-remote-issue-links/
- https://developer.atlassian.com/server/jira/platform/using-fields-in-remote-issue-links/

---

## Part 1: Issue Links (between Jira issues)

Issue links connect two Jira issues with a typed relationship (e.g., "blocks", "duplicates").

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rest/api/2/issueLink` | Create issue link |
| GET | `/rest/api/2/issueLink/{linkId}` | Get issue link by ID |
| DELETE | `/rest/api/2/issueLink/{linkId}` | Delete issue link by ID |

### Create Issue Link

**`POST /rest/api/2/issueLink`**

Creates a link between two issues. Returns `201` with no response body.

To obtain the ID of the created link, fetch one of the linked issues with `?fields=issuelinks`.

If the link duplicates an existing link, the response still returns `201`.

Request body:

```json
{
  "type": {
    "name": "Blocks"
  },
  "inwardIssue": {
    "key": "PROJ-123"
  },
  "outwardIssue": {
    "key": "PROJ-456"
  },
  "comment": {
    "body": "Linked related issue!",
    "visibility": {
      "type": "group",
      "value": "jira-software-users"
    }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type.name` | string | Yes | Link type name (e.g., `"Blocks"`, `"Duplicate"`, `"Cloners"`) |
| `type.id` | string | Alt | Link type ID (alternative to `name`) |
| `inwardIssue.key` | string | Yes | Issue key for inward side |
| `outwardIssue.key` | string | Yes | Issue key for outward side |
| `comment` | object | No | Optional comment added to the inward issue |
| `comment.body` | string | No | Comment text (plain text in v2, ADF in v3) |
| `comment.visibility` | object | No | Restrict comment visibility to group/role |

Status codes:

| Code | Meaning |
|------|---------|
| 201 | Link created successfully (no body) |
| 400 | Invalid input |
| 401 | Authentication required |
| 404 | Issue not found or issue linking disabled |

### Get Issue Link

**`GET /rest/api/2/issueLink/{linkId}`**

Returns `200` with the full link details.

Response body:

```json
{
  "id": "10001",
  "self": "https://host/rest/api/2/issueLink/10001",
  "type": {
    "id": "10000",
    "name": "Blocks",
    "inward": "is blocked by",
    "outward": "blocks",
    "self": "https://host/rest/api/2/issueLinkType/10000"
  },
  "inwardIssue": {
    "id": "10230",
    "key": "PROJ-123",
    "self": "https://host/rest/api/2/issue/10230",
    "fields": {
      "summary": "Issue summary",
      "status": { "name": "Open", "id": "1" },
      "priority": { "name": "Major", "id": "3" },
      "issuetype": { "name": "Bug", "id": "1", "subtask": false }
    }
  },
  "outwardIssue": {
    "id": "10231",
    "key": "PROJ-456",
    "self": "https://host/rest/api/2/issue/10231",
    "fields": {
      "summary": "Other issue",
      "status": { "name": "Open", "id": "1" },
      "priority": { "name": "Major", "id": "3" },
      "issuetype": { "name": "Bug", "id": "1", "subtask": false }
    }
  }
}
```

### Delete Issue Link

**`DELETE /rest/api/2/issueLink/{linkId}`**

Returns `200` or `204` with no body.

| Code | Meaning |
|------|---------|
| 200/204 | Link deleted |
| 401 | Authentication required |
| 404 | Link not found |

### Alternative: Manage Links via Issue Update

Links can also be created/removed via `PUT /rest/api/2/issue/{key}`:

```json
{
  "update": {
    "issuelinks": [
      {
        "add": {
          "type": { "name": "Blocks" },
          "outwardIssue": { "key": "PROJ-456" }
        }
      },
      {
        "remove": { "id": "10001" }
      }
    ]
  }
}
```

### Issue Links in GET Issue Response

When fetching an issue, links appear in `fields.issuelinks`:

```json
{
  "fields": {
    "issuelinks": [
      {
        "id": "10001",
        "self": "https://host/rest/api/2/issueLink/10001",
        "type": {
          "id": "10000",
          "name": "Blocks",
          "inward": "is blocked by",
          "outward": "blocks"
        },
        "outwardIssue": {
          "key": "PROJ-456",
          "self": "https://host/rest/api/2/issue/10231",
          "fields": {
            "summary": "Other issue",
            "status": { "name": "Open" },
            "priority": { "name": "Major" },
            "issuetype": { "name": "Bug" }
          }
        }
      }
    ]
  }
}
```

Each link object contains either `inwardIssue` or `outwardIssue` (never both) depending on the perspective of the current issue.

---

## Part 2: Issue Link Types

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/issueLinkType` | List all link types |
| GET | `/rest/api/2/issueLinkType/{id}` | Get link type by ID |
| POST | `/rest/api/2/issueLinkType` | Create link type |
| PUT | `/rest/api/2/issueLinkType/{id}` | Update link type |
| DELETE | `/rest/api/2/issueLinkType/{id}` | Delete link type |

### List Link Types

**`GET /rest/api/2/issueLinkType`**

Response:

```json
{
  "issueLinkTypes": [
    {
      "id": "10000",
      "name": "Blocks",
      "inward": "is blocked by",
      "outward": "blocks",
      "self": "https://host/rest/api/2/issueLinkType/10000"
    },
    {
      "id": "10001",
      "name": "Duplicate",
      "inward": "is duplicated by",
      "outward": "duplicates",
      "self": "https://host/rest/api/2/issueLinkType/10001"
    }
  ]
}
```

### Link Type Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique ID (server-generated) |
| `name` | string | Type name (e.g., `"Blocks"`) |
| `inward` | string | Label when this issue is the target (e.g., `"is blocked by"`) |
| `outward` | string | Label when this issue is the source (e.g., `"blocks"`) |
| `self` | string | URL to this link type resource |

### Create / Update Link Type

**`POST /rest/api/2/issueLinkType`** — Returns `201`
**`PUT /rest/api/2/issueLinkType/{id}`** — Returns `200`

Request body (same for both):

```json
{
  "name": "Blocks",
  "inward": "is blocked by",
  "outward": "blocks"
}
```

---

## Part 3: Remote Issue Links (links to external systems)

Remote links connect a Jira issue to an object in an external system (URLs, support tickets, CI builds, etc.). They are distinct from issue links, which connect two Jira issues.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rest/api/2/issue/{issueIdOrKey}/remotelink` | List all remote links |
| GET | `/rest/api/2/issue/{issueIdOrKey}/remotelink?globalId={id}` | Get remote link by globalId |
| GET | `/rest/api/2/issue/{issueIdOrKey}/remotelink/{linkId}` | Get remote link by internal ID |
| POST | `/rest/api/2/issue/{issueIdOrKey}/remotelink` | Create (or upsert) remote link |
| PUT | `/rest/api/2/issue/{issueIdOrKey}/remotelink/{linkId}` | Update remote link by ID |
| DELETE | `/rest/api/2/issue/{issueIdOrKey}/remotelink/{linkId}` | Delete remote link by ID |
| DELETE | `/rest/api/2/issue/{issueIdOrKey}/remotelink?globalId={id}` | Delete remote link by globalId |

### Remote Link JSON Schema

Full request body for create/update:

```json
{
  "globalId": "system=http://www.mycompany.com/support&id=1",
  "application": {
    "type": "com.acme.tracker",
    "name": "My Acme Tracker"
  },
  "relationship": "causes",
  "object": {
    "url": "http://www.mycompany.com/support?id=1",
    "title": "TSTSUP-111",
    "summary": "Customer support issue",
    "icon": {
      "url16x16": "http://www.mycompany.com/support/ticket.png",
      "title": "Support Ticket"
    },
    "status": {
      "resolved": true,
      "icon": {
        "url16x16": "http://www.mycompany.com/support/resolved.png",
        "title": "Case Closed",
        "link": "http://www.mycompany.com/support?id=1&details=closed"
      }
    }
  }
}
```

### Field Reference

#### Top-level fields

| Field | Type | Required | Max Length | Description |
|-------|------|----------|------------|-------------|
| `globalId` | string | Strongly recommended | 255 chars | Uniquely identifies the remote app + remote object. Used for upsert, get-by-globalId, and delete-by-globalId. Must be unique per issue. |
| `application` | object | Strongly recommended | — | Information about the source application |
| `application.type` | string | Strongly recommended | — | Namespaced app identifier (e.g., `"com.acme.tracker"`). Used by custom renderers. |
| `application.name` | string | Strongly recommended | — | Human-readable app name. Used for grouping links in the UI and in icon tooltips. |
| `relationship` | string | No | — | Describes the relationship (e.g., `"causes"`, `"is caused by"`). Groups links in the UI. Defaults to `"links to"` if blank. |

#### `object` fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `object.url` | string (URL) | **Yes** | Hyperlink to the remote object |
| `object.title` | string | **Yes** | Display name of the remote object |
| `object.summary` | string | No | Summary text displayed after the title |
| `object.icon` | object | Strongly recommended | Icon for the remote object |
| `object.icon.url16x16` | string (URL) | Strongly recommended | URL to a 16x16 icon image. Default link icon used if blank. |
| `object.icon.title` | string | Strongly recommended | Tooltip for the icon |
| `object.status` | object | No | Status information for the remote object |
| `object.status.resolved` | boolean | No | If `true`, title is rendered with strikethrough |
| `object.status.icon` | object | No | Icon representing the status |
| `object.status.icon.url16x16` | string (URL) | No | URL to a 16x16 status icon |
| `object.status.icon.title` | string | No | Tooltip for the status icon |
| `object.status.icon.link` | string (URL) | No | Makes the status icon clickable |

### Create Remote Link

**`POST /rest/api/2/issue/{issueIdOrKey}/remotelink`**

Minimum request body (only `object.url` and `object.title` are required):

```json
{
  "object": {
    "url": "https://www.example.com",
    "title": "Example Link"
  }
}
```

**Upsert behavior:** If the request includes a `globalId` that matches an existing remote link on the same issue, the existing link is updated instead of creating a new one.

Response (`201`):

```json
{
  "id": 10000,
  "self": "https://host/rest/api/2/issue/PROJ-1/remotelink/10000"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Server-generated internal ID |
| `self` | string (URL) | URL to this remote link resource (uses issue key in path) |

### Update Remote Link

**`PUT /rest/api/2/issue/{issueIdOrKey}/remotelink/{linkId}`**

Same request body as create. Fields not present in the request are set to `null` (full replacement, not merge).

Response (`200`): Same `{ "id", "self" }` shape as create.

Can also update via POST with matching `globalId` (upsert).

### Get Remote Link by ID

**`GET /rest/api/2/issue/{issueIdOrKey}/remotelink/{linkId}`**

Response (`200`):

```json
{
  "id": 10000,
  "self": "https://host/rest/api/2/issue/PROJ-1/remotelink/10000",
  "globalId": "system=http://www.mycompany.com/support&id=1",
  "application": {
    "type": "com.acme.tracker",
    "name": "My Acme Tracker"
  },
  "relationship": "causes",
  "object": {
    "url": "http://www.mycompany.com/support?id=1",
    "title": "TSTSUP-111",
    "summary": "Customer support issue",
    "icon": {
      "url16x16": "http://www.mycompany.com/support/ticket.png",
      "title": "Support Ticket"
    },
    "status": {
      "resolved": true,
      "icon": {
        "url16x16": "http://www.mycompany.com/support/resolved.png",
        "title": "Case Closed",
        "link": "http://www.mycompany.com/support?id=1&details=closed"
      }
    }
  }
}
```

### Get Remote Link by globalId

**`GET /rest/api/2/issue/{issueIdOrKey}/remotelink?globalId={urlEncodedGlobalId}`**

Returns a single remote link object (same shape as get-by-ID). The `globalId` query parameter must be URL-encoded.

### List All Remote Links

**`GET /rest/api/2/issue/{issueIdOrKey}/remotelink`**

Response (`200`): JSON array of remote link objects (same shape as individual get).

### Delete Remote Link

**By internal ID:** `DELETE /rest/api/2/issue/{issueIdOrKey}/remotelink/{linkId}`
**By globalId:** `DELETE /rest/api/2/issue/{issueIdOrKey}/remotelink?globalId={urlEncodedGlobalId}`

Returns `204` with no body.

### Status Codes (all remote link endpoints)

| Code | Meaning |
|------|---------|
| 200 | Success (GET, PUT) |
| 201 | Created (POST) |
| 204 | Deleted (DELETE) |
| 400 | Invalid request (e.g., missing `object.url`) |
| 401 | Authentication required |
| 403 | Insufficient permissions (need Browse Projects + Link Issues) |
| 404 | Issue or remote link not found |

### Permissions

All remote link operations require:
- **Browse projects** project permission
- **Link issues** project permission
- If issue-level security is configured, the user must have permission to view the issue

### v2 vs v3 Differences

The remote link endpoints behave identically in v2 and v3. Unlike issue description/comment fields, remote link fields do not use ADF, so there is no behavioral difference between API versions.

---

## Part 4: Atlassian Rovo MCP Server — Link Tools

The official Atlassian Rovo MCP Server (cloud-hosted, OAuth 2.1) exposes link-related
functionality through the following tools. Documentation:
https://support.atlassian.com/atlassian-rovo-mcp-server/docs/supported-tools/

### Read tools (`read_jira` permission group, scope `read:jira-work`)

| Tool | Description |
|------|-------------|
| `getJiraIssueRemoteIssueLinks` | List remote issue links (e.g., Confluence links) on a Jira issue |
| `getIssueLinkTypes` | List available issue link types (Blocks, Duplicates, etc.) |

`getJiraIssueRemoteIssueLinks` takes an `issueIdOrKey` parameter and returns the
remote link array for that issue.

`getIssueLinkTypes` takes no parameters and returns the list of configured link
types with their `id`, `name`, `inward`, and `outward` labels.

### Write tools (`write_jira` permission group, scope `write:jira-work`)

There is **no dedicated MCP tool** for creating, updating, or deleting issue links
or remote links. As of the current beta, passing `update.issuelinks` through
`editJiraIssue` is accepted but silently ignored — creating/editing links via MCP
is a known limitation on Atlassian's backlog.

The write tools that exist (`createJiraIssue`, `editJiraIssue`, `addCommentToJiraIssue`,
`transitionJiraIssue`, `addWorklogToJiraIssue`) do not support link operations.

### Complete Rovo MCP tool list (for reference)

All Jira tools exposed by the official Atlassian Rovo MCP Server:

**`read_jira`** (scope: `read:jira-work`)

| Tool | Description |
|------|-------------|
| `getJiraIssue` | Get a Jira issue by ID or key |
| `getJiraIssueRemoteIssueLinks` | List remote issue links on an issue |
| `getIssueLinkTypes` | List available issue link types |
| `getJiraIssueTypeMetaWithFields` | Get create-field metadata for a project and issue type |
| `getJiraProjectIssueTypesMetadata` | List issue types available in a Jira project |
| `getTransitionsForJiraIssue` | List available workflow transitions for an issue |
| `getVisibleJiraProjects` | List Jira projects the user can access |
| `lookupJiraAccountId` | Find Jira user account IDs by name or email |

**`write_jira`** (scope: `write:jira-work`)

| Tool | Description |
|------|-------------|
| `createJiraIssue` | Create a new Jira issue |
| `editJiraIssue` | Update fields on an existing Jira issue |
| `addCommentToJiraIssue` | Add a comment to a Jira issue |
| `transitionJiraIssue` | Perform a workflow transition on an issue |
| `addWorklogToJiraIssue` | Add a time-tracking worklog to a Jira issue |

**`search_jira`** (scope: `search:jira-work`)

| Tool | Description |
|------|-------------|
| `searchJiraIssuesUsingJql` | Search Jira issues using a JQL query |
