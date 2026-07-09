# Project Components API Implementation Plan

## Goal

Implement Jira-compatible project component endpoints described in `references/jira-project-components-api-specification.md`, starting with the compatibility path required by RHAI component tooling:

```http
GET /rest/api/3/project/{projectIdOrKey}/components
```

The emulator should implement the route under `/rest/api/2`; the existing API version rewrite middleware will make the `/rest/api/3` path work.

## Current State

The data model and issue behavior already exist:

- `Component` stores project-scoped component names and optional metadata.
- `IssueComponent` associates issues with components.
- Issue create, issue update, and import paths create missing components by name.
- Issue responses include `fields.components`.
- The frontend displays issue components.

The missing work is the Jira component management API surface.

## Phase 1 - Shared Component Serialization

Add a small serializer, either in `src/jira_emulator/routers/projects.py` or a dedicated component service module, that converts a `Component` model into a Jira-compatible response object.

Required fields:

- `self`
- `id`
- `name`
- `description`
- `project`
- `projectId`
- `assigneeType`
- `realAssigneeType`
- `isAssigneeTypeValid`

Default unsupported assignment fields to:

```json
{
  "assigneeType": "PROJECT_DEFAULT",
  "realAssigneeType": "PROJECT_DEFAULT",
  "isAssigneeTypeValid": true
}
```

Reuse this serializer in existing project detail output so component responses stay consistent.

## Phase 2 - Project Component List Endpoint

Implement:

```http
GET /rest/api/2/project/{projectIdOrKey}/components
```

Behavior:

- Resolve project by key or numeric id using existing project lookup.
- Return `404` with Jira-style error body when the project does not exist.
- Return a JSON array of component objects.
- Sort by component name case-insensitively for deterministic output.
- Accept `componentSource` and ignore it.

Tests:

- `GET /rest/api/2/project/{key}/components` returns `200` and an array.
- `GET /rest/api/3/project/{key}/components` also works through middleware.
- Components created through issue import or issue creation appear in the endpoint.
- Unknown project returns `404`.

## Phase 3 - Create Component Endpoint

Implement:

```http
POST /rest/api/2/component
```

Request body:

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

Behavior:

- Require `name` and `project`.
- Resolve `project` as a project key.
- Create `Component(project_id, name, description, lead)`.
- Preserve `description`.
- Map `leadUserName` to current `Component.lead` if supplied.
- Accept but ignore `assigneeType` and `leadAccountId` for now.
- Return `201` with the component object.
- Return `400` for duplicates in the same project.
- Return `404` for missing projects.

Tests:

- Creating a component returns `201`.
- Created component appears in project component list and project detail.
- Duplicate name in the same project returns `400`.
- Same component name can be created in another project.
- Missing `name` or `project` returns `400`.

## Phase 4 - Single Component Read and Update

Implement:

```http
GET /rest/api/2/component/{id}
PUT /rest/api/2/component/{id}
```

GET behavior:

- Return one component object.
- Return `404` when not found.

PUT behavior:

- Update included fields only.
- Support `name`, `description`, and `leadUserName`.
- Accept but ignore `assigneeType`, `leadAccountId`, and empty lead removal unless model support is expanded.
- Reject `project` changes initially with `400` because moving a component across projects can invalidate existing issue associations.
- Enforce same-project unique component names.
- Return `200` with updated component object.

Tests:

- Component can be fetched by id.
- Component can be renamed.
- Renaming affects issue responses because issues reference component id.
- Updating to a duplicate same-project name returns `400`.
- Moving component to another project returns `400`.

## Phase 5 - Paginated Component Reads

Implement:

```http
GET /rest/api/2/project/{projectIdOrKey}/component
GET /rest/api/2/component
```

Behavior:

- Support `startAt`, `maxResults`, `orderBy`, and `query`.
- For project-scoped endpoint, resolve one project first.
- For global endpoint, support no project filter initially, then add `projectIdsOrKeys`.
- Include `issueCount` for project-scoped paginated values.
- Include `nextPage` when another page exists.

Tests:

- Pagination returns correct `startAt`, `maxResults`, `total`, `isLast`, and `values`.
- `query` filters by component name substring.
- `orderBy=name` and `orderBy=-name` sort deterministically.
- `projectIdsOrKeys` limits global results.

## Phase 6 - Delete and Related Issue Count

Implement:

```http
DELETE /rest/api/2/component/{id}
GET /rest/api/2/component/{id}/relatedIssueCounts
```

Delete behavior:

- Without `moveIssuesTo`, remove issue associations and delete the component.
- With `moveIssuesTo`, validate target exists in the same project, copy issue associations to target without duplicates, then delete the source component.
- Return `204`.

Issue count behavior:

- Count unique issues associated with the component.
- Return `{ "self": "...", "issueCount": N }`.

Tests:

- Issue count reflects issue associations.
- Deleting without `moveIssuesTo` removes component from affected issue responses.
- Deleting with `moveIssuesTo` moves associations to the target component.
- Invalid target component returns `400` or `404` as appropriate.

## Import and Issue Behavior Audit

Before finishing the feature, audit existing issue/import code for edge cases:

- Deduplicate repeated component names within one issue create request.
- Deduplicate repeated component names within one issue update replacement request.
- Deduplicate repeated component names within one imported issue payload.
- Ensure import replacement removes associations no longer present.
- Ensure imported components with only `id` and no `name` are skipped or documented.

Add regression tests for:

- Import creates a missing component row and displays it in issue response.
- Re-importing the same issue does not duplicate `IssueComponent` rows.
- Issue create/update with repeated component names associates the component once.

## Frontend Impact

No new frontend view is required for the first compatibility target.

Expected frontend behavior:

- Existing issue detail component display should continue working because it reads `fields.components`.
- Components created by import or API should appear on issue detail pages.
- If a component is renamed through `PUT /component/{id}`, issue detail pages should show the new name.

Potential future frontend work:

- Add project component list to the project page.
- Add component create/edit/delete controls to the admin interface.

## Implementation Order

1. Add serializer and route tests for `GET /project/{key}/components`.
2. Implement `GET /project/{key}/components`.
3. Add create component tests.
4. Implement `POST /component`.
5. Add single component read/update tests and implementation.
6. Add issue/import deduplication tests and fixes.
7. Add paginated endpoints if needed by clients.
8. Add delete/count endpoints if lifecycle management is needed by clients.

## Verification

Run focused tests after each phase:

```bash
uv run pytest tests/test_projects.py tests/test_import.py tests/test_issues.py tests/test_update_ops.py
```

Run lint on changed Python files:

```bash
uv run ruff check src tests
```

Run the full suite before committing:

```bash
uv run pytest
```

## Open Questions

- Should `POST /component` preserve remote Jira component ids during imports, or should local ids remain authoritative?
- Should `project` changes in `PUT /component/{id}` be rejected permanently, or implemented later with association migration rules?
- Should the emulator enforce project admin permissions for component create/update/delete, or continue using the existing coarse authentication model?
- Should component assignment fields be persisted now, or are stable defaults enough for current clients?
