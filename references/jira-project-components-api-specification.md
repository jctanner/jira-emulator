# Jira REST API - Project Components Specification

Collected from Atlassian Jira Cloud REST API v3 documentation and local emulator behavior, July 2026.

## Sources

- https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-project-components/
- `/tmp/jira-rhai-components-api.md`
- `src/jira_emulator/models/component.py`
- `src/jira_emulator/services/issue_service.py`
- `src/jira_emulator/services/import_service.py`
- `src/jira_emulator/routers/projects.py`

## Purpose

Project components are named containers that belong to a Jira project and can be assigned to issues through the issue `fields.components` array. The emulator already stores components and issue-to-component associations, and issue create/update/import paths already create missing component rows when an issue references a component by name.

The missing compatibility surface is the Jira project components API, especially:

```http
GET /rest/api/3/project/{projectIdOrKey}/components
```

The emulator rewrites `/rest/api/3/...` to `/rest/api/2/...`, so implementation should register v2 routes and allow the existing middleware to make v3 clients work.

## Current Emulator State

Implemented today:

- `Component` model with `id`, `project_id`, `name`, `description`, and `lead`.
- Unique constraint on `(project_id, name)`.
- `IssueComponent` join model mapping issues to components.
- `GET /rest/api/2/project/{projectIdOrKey}` embeds a `components` array in the project detail response.
- `POST /rest/api/2/issue` accepts `fields.components` and creates missing project components by name.
- `PUT /rest/api/2/issue/{issueIdOrKey}` accepts `fields.components` as a full replacement and creates missing project components by name.
- `PUT /rest/api/2/issue/{issueIdOrKey}` accepts `update.components[].add` and creates missing project components by name.
- Import service replaces issue component associations and creates missing project components by name.
- Issue detail responses and the frontend display `fields.components`.

Missing today:

- `GET /rest/api/2/project/{projectIdOrKey}/components`
- `GET /rest/api/2/project/{projectIdOrKey}/component`
- `GET /rest/api/2/component`
- `POST /rest/api/2/component`
- `GET /rest/api/2/component/{id}`
- `PUT /rest/api/2/component/{id}`
- `DELETE /rest/api/2/component/{id}`
- `GET /rest/api/2/component/{id}/relatedIssueCounts`

## Endpoint Summary

| Method | Path | Priority | Description |
|--------|------|----------|-------------|
| GET | `/rest/api/2/project/{projectIdOrKey}/components` | P0 | Return all components for one project. Required by RHAI component fetch tooling. |
| GET | `/rest/api/2/project/{projectIdOrKey}/component` | P1 | Return paginated components for one project. |
| GET | `/rest/api/2/component` | P1 | Return paginated components across selected projects. |
| POST | `/rest/api/2/component` | P0/P1 | Create a component. Needed if clients pre-create components before assigning them to issues. |
| GET | `/rest/api/2/component/{id}` | P1 | Return one component by id. |
| PUT | `/rest/api/2/component/{id}` | P1 | Update one component by id. Jira uses PUT, not PATCH. |
| DELETE | `/rest/api/2/component/{id}` | P2 | Delete one component by id, optionally moving issue associations. |
| GET | `/rest/api/2/component/{id}/relatedIssueCounts` | P2 | Return count of issues assigned to a component. |

## Component Object

The local emulator should return a Jira-compatible component object. Fields not represented in the database can be omitted or returned with stable defaults.

Recommended response shape:

```json
{
  "self": "http://jira.local/rest/api/2/component/123",
  "id": "123",
  "name": "AI Core Platform",
  "description": "",
  "assigneeType": "PROJECT_DEFAULT",
  "realAssigneeType": "PROJECT_DEFAULT",
  "isAssigneeTypeValid": true,
  "project": "RHAI",
  "projectId": 42
}
```

Optional user objects such as `assignee`, `realAssignee`, and `lead` may be omitted initially because the current `Component` model only has a free-form `lead` string and the RHAI component consumer only needs `name`.

If included, user objects should follow the existing emulator user response conventions rather than inventing a separate shape.

## GET Project Components

```http
GET /rest/api/2/project/{projectIdOrKey}/components
GET /rest/api/3/project/{projectIdOrKey}/components
```

The v3 path should work through the existing rewrite middleware.

### Request

Path parameters:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `projectIdOrKey` | string | Yes | Project key such as `RHAI`, or numeric project id. |

Query parameters:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `componentSource` | string | No | Jira Cloud source selector for Compass/project components. The emulator can accept and ignore it. |

### Response

Status `200` with an array of component objects:

```json
[
  {
    "self": "http://jira.local/rest/api/2/component/1",
    "id": "1",
    "name": "AI Core Platform",
    "description": "",
    "assigneeType": "PROJECT_DEFAULT",
    "realAssigneeType": "PROJECT_DEFAULT",
    "isAssigneeTypeValid": true,
    "project": "RHAI",
    "projectId": 10000
  }
]
```

Sorting should be deterministic. Sort by component name ascending, case-insensitive, unless matching Jira insertion order becomes necessary for compatibility.

Status codes:

| Code | Meaning |
|------|---------|
| 200 | Project found; component list returned. Empty list is valid. |
| 401 | Authentication required. |
| 404 | Project id/key not found. |

### RHAI Compatibility

The script described in `/tmp/jira-rhai-components-api.md` fetches this endpoint, extracts `name` from each object, sorts names, and writes `.context/rhai-components.txt`. The emulator must therefore include at least `id`, `name`, and `self` in every returned component. Including `project` and `projectId` makes the response closer to Jira Cloud.

## GET Project Components Paginated

```http
GET /rest/api/2/project/{projectIdOrKey}/component
GET /rest/api/3/project/{projectIdOrKey}/component
```

### Request

Path parameters:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `projectIdOrKey` | string | Yes | Project key or numeric project id. |

Query parameters:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `startAt` | integer | No | Zero-based offset. Default `0`. |
| `maxResults` | integer | No | Page size. Default `50`. |
| `orderBy` | string | No | Jira supports ordering. Emulator can initially support `name` and `-name`, ignoring unsupported values or returning `400`. |
| `query` | string | No | Filter components by name substring. |
| `componentSource` | string | No | Accept and ignore initially. |

### Response

Status `200` with a page object:

```json
{
  "self": "http://jira.local/rest/api/2/project/RHAI/component?startAt=0&maxResults=50",
  "startAt": 0,
  "maxResults": 50,
  "total": 1,
  "isLast": true,
  "values": [
    {
      "self": "http://jira.local/rest/api/2/component/1",
      "id": "1",
      "name": "AI Core Platform",
      "description": "",
      "issueCount": 12,
      "assigneeType": "PROJECT_DEFAULT",
      "realAssigneeType": "PROJECT_DEFAULT",
      "isAssigneeTypeValid": true,
      "project": "RHAI",
      "projectId": 10000
    }
  ]
}
```

`nextPage` should be included when another page exists. `issueCount` is useful here because Jira's paginated project component response uses a component-with-issue-count shape.

## GET Components Across Projects

```http
GET /rest/api/2/component
GET /rest/api/3/component
```

### Request

Query parameters:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `projectIdsOrKeys` | array/string | No | Jira accepts one or more project ids/keys. The emulator should tolerate repeated params and comma-separated input. |
| `startAt` | integer | No | Zero-based offset. Default `0`. |
| `maxResults` | integer | No | Page size. Default `50`. |
| `orderBy` | string | No | Support `name` and `-name` initially. |
| `query` | string | No | Filter components by name substring. |

### Response

Status `200` with a page object:

```json
{
  "self": "http://jira.local/rest/api/2/component?startAt=0&maxResults=50",
  "startAt": 0,
  "maxResults": 50,
  "total": 1,
  "isLast": true,
  "values": [
    {
      "self": "http://jira.local/rest/api/2/component/1",
      "id": "1",
      "name": "AI Core Platform",
      "description": "",
      "project": "RHAI",
      "projectId": 10000
    }
  ]
}
```

## POST Create Component

```http
POST /rest/api/2/component
POST /rest/api/3/component
```

### Request

```json
{
  "name": "AI Core Platform",
  "project": "RHAI",
  "description": "Optional description",
  "assigneeType": "PROJECT_DEFAULT",
  "leadAccountId": "optional-account-id",
  "leadUserName": "optional-username"
}
```

Fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Component name. Must be unique within the project. |
| `project` | string | Yes | Project key. Jira documents this as the project key. |
| `description` | string | No | Stored in `Component.description`. |
| `assigneeType` | string | No | Accept and preserve only if a model field is added; otherwise ignore and return default. |
| `leadAccountId` | string | No | Jira Cloud lead account. Can be ignored initially. |
| `leadUserName` | string | No | Legacy Jira username. May map to `Component.lead` if useful. |

### Response

Status `201` with the created component object.

Status codes:

| Code | Meaning |
|------|---------|
| 201 | Component created. |
| 400 | Missing name/project, invalid JSON, or duplicate component name in the project. |
| 401 | Authentication required. |
| 403 | Authenticated user lacks admin permission. The emulator may not enforce this separately. |
| 404 | Project not found. |

### Duplicate Handling

Jira returns an error when creating a duplicate component in the same project. The emulator should not silently return the existing component from `POST /component`; issue create/update/import paths may still auto-create-or-reuse by name.

## GET Component

```http
GET /rest/api/2/component/{id}
GET /rest/api/3/component/{id}
```

Return one component object by numeric id.

Status codes:

| Code | Meaning |
|------|---------|
| 200 | Component found. |
| 401 | Authentication required. |
| 404 | Component not found. |

## PUT Update Component

```http
PUT /rest/api/2/component/{id}
PUT /rest/api/3/component/{id}
```

Jira documents component updates as `PUT`, not `PATCH`. Included fields overwrite the existing values. Omitted fields are unchanged.

### Request

```json
{
  "name": "AI Core Platform Security",
  "project": "RHAI",
  "description": "Updated description",
  "assigneeType": "PROJECT_DEFAULT",
  "leadAccountId": "",
  "leadUserName": ""
}
```

Fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | New name. Must remain unique within the target project. |
| `project` | string | No | Move component to another project if supported. P1 implementation may reject project moves with `400`. |
| `description` | string | No | Replacement description. |
| `assigneeType` | string | No | Accept and ignore unless persisted. |
| `leadAccountId` | string | No | Empty string removes lead in Jira. |
| `leadUserName` | string | No | Legacy lead field. |

### Response

Status `200` with updated component object.

### Issue Impact

Renaming a component should not alter issue associations because issues point to `component_id`. Existing issue responses and frontend display should automatically show the new name.

If a component is moved to another project, existing issue associations become problematic because associated issues still belong to the old project. Initial implementation should reject project changes unless there is a clear use case.

## DELETE Component

```http
DELETE /rest/api/2/component/{id}
DELETE /rest/api/3/component/{id}
```

### Request

Query parameters:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `moveIssuesTo` | string | No | Component id to assign affected issues to before deleting this component. |

### Behavior

If `moveIssuesTo` is absent, delete issue associations for this component and then delete the component.

If `moveIssuesTo` is present:

1. Validate both components exist.
2. Validate both components belong to the same project.
3. For every issue associated with the deleted component, create an association to the target component if one does not already exist.
4. Remove associations to the deleted component.
5. Delete the component.

Response status is `204` with no body.

## GET Component Related Issue Counts

```http
GET /rest/api/2/component/{id}/relatedIssueCounts
GET /rest/api/3/component/{id}/relatedIssueCounts
```

Return the number of issues assigned to a component:

```json
{
  "self": "http://jira.local/rest/api/2/component/1",
  "issueCount": 23
}
```

Count unique issue ids from `issue_components`.

## Relationship to Issues

Issues reference components through `fields.components`.

Create issue request:

```json
{
  "fields": {
    "project": {"key": "RHAI"},
    "summary": "Example",
    "issuetype": {"name": "Task"},
    "components": [
      {"name": "AI Core Platform"}
    ]
  }
}
```

Update issue replacement:

```json
{
  "fields": {
    "components": [
      {"name": "AI Core Platform"},
      {"name": "Documentation"}
    ]
  }
}
```

Update issue operation:

```json
{
  "update": {
    "components": [
      {"add": {"name": "AI Core Platform"}},
      {"remove": {"name": "Documentation"}}
    ]
  }
}
```

Expected behavior:

- Component names are project-scoped.
- If an issue references a component name that does not exist in its project, the emulator creates the component automatically.
- Issue responses include component objects under `fields.components`.
- Frontend issue detail pages display `fields.components`.
- JQL `component = "AI Core Platform"` should match issues through `IssueComponent`.
- Duplicate component associations on the same issue should be avoided. If an issue payload repeats the same component name, the emulator should associate it once.

## Relationship to Imports

Imported issue payloads may include components in either normalized or Jira REST style:

```json
{
  "key": "RHAI-123",
  "fields": {
    "project": {"key": "RHAI"},
    "components": [
      {"name": "AI Core Platform"},
      {"id": "10001", "name": "Documentation"}
    ]
  }
}
```

or:

```json
{
  "key": "RHAI-123",
  "project": "RHAI",
  "components": [
    {"name": "AI Core Platform"},
    "Documentation"
  ]
}
```

Expected import behavior:

- Resolve the issue project before resolving components.
- For each component entry, prefer `name`.
- If only `id` is present, the emulator may ignore it initially unless component id preservation is implemented.
- Create a missing `Component(project_id, name)` row before creating `IssueComponent`.
- Reuse an existing component with the same project and name.
- Replace the issue's component associations on re-import so removed components disappear.
- Deduplicate repeated component names in the same imported issue payload.
- Preserve component `description` only when the import format supplies project component metadata; issue fields usually include only component references.

The current import service already creates missing components by name and replaces issue associations. It should be reviewed for duplicate names in one payload and expanded only if project-level component metadata imports are added.

## Data Model Guidance

Current model:

```text
components
  id integer primary key
  project_id integer foreign key projects.id
  name string
  description text nullable
  lead string nullable
  unique(project_id, name)

issue_components
  issue_id integer foreign key issues.id
  component_id integer foreign key components.id
  primary key(issue_id, component_id)
```

This is enough for the P0 endpoint and basic CRUD.

Potential future fields:

- `assignee_type`
- `real_assignee_type`
- `lead_account_id`
- `metadata`
- external Jira component id, if imports need to preserve remote ids separately from local autoincrement ids.

## Implementation Plan

1. Add component serialization helper shared by project detail and component routes.
2. Add component lookup helper by numeric id, returning Jira-format `404`.
3. Add `GET /project/{projectIdOrKey}/components`.
4. Add tests proving `/rest/api/2/project/{key}/components` and `/rest/api/3/project/{key}/components` return the same array.
5. Add `POST /component` with duplicate validation.
6. Add tests proving created components appear in project component list, project detail, and issue component selection.
7. Add paginated read endpoints if client compatibility requires them.
8. Add PUT/DELETE/count endpoints if clients manage component lifecycle directly.

## Acceptance Criteria

- `GET /rest/api/3/project/RHAI/components` works through the v3 rewrite middleware.
- The response is an array, not a page object.
- Each element includes at least `self`, `id`, `name`, `description`, `project`, and `projectId`.
- Project-not-found returns a Jira-style `404`.
- `POST /rest/api/3/component` can create a component for a project.
- Duplicate create attempts in the same project return `400`.
- Creating an issue with `fields.components` creates or reuses project component rows.
- Updating an issue with `fields.components` replaces component associations and creates missing component rows.
- Importing an issue with `fields.components` creates or reuses project component rows so the component appears in API responses and the frontend.
- Re-importing the same issue does not duplicate issue-component associations.
- Component names remain project-scoped; the same name can exist in different projects.
