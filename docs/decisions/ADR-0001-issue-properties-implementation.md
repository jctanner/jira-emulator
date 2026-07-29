# ADR-0001: Issue Properties Implementation

## Status

Accepted

## Context

The Jira emulator lacked support for issue properties (entity properties), a key-value store that allows arbitrary JSON data to be attached to issues. This is a core Jira REST API feature used by apps, integrations, automation rules, and MCP-based AI agents to store metadata on issues without polluting custom fields.

Without properties support, clients that depend on `GET/PUT/DELETE /rest/api/2/issue/{key}/properties/{propertyKey}` would get 404s, and JQL queries using `issue.property[key].path` syntax would fail.

## Decision

Implement per-issue property CRUD following the Atlassian Swagger v3 specification, stored as a new `issue_properties` SQLite table with JSON values serialized as text.

Key design choices:

1. **Single table, JSON-as-text**: Property values are stored as serialized JSON strings in a `TEXT` column rather than using SQLite's JSON1 column type. This keeps the model simple and consistent with how the emulator stores other flexible data (e.g., custom field JSON values). SQLite's `json_extract()` is used at query time for JQL path traversal.

2. **No separate service layer**: The router handles DB operations directly, following the `remote_links.py` pattern rather than the heavier `issue_service.py` pattern. Properties are simple key-value CRUD with no business logic beyond validation.

3. **JQL via grammar extension**: Added a `PROPERTY_FIELD` terminal to the Lark grammar (`issue.property[key].sub.path`) with priority 3 to match before the generic `FIELD_NAME` rule. The transformer uses `json_extract()` subqueries against the properties table.

4. **Expansion over inclusion**: Properties are exposed on `GET /issue/{key}` via `?expand=properties` (top-level `properties` key in the response) rather than as a field inside `fields`. This matches Jira's actual behavior where properties are a separate concern from issue fields.

5. **Import service support**: The importer accepts a `properties` dict on issue JSON payloads, enabling bulk loading of property data. Properties are replaced (not merged) on re-import, consistent with how labels, components, and custom fields are handled.

6. **Bulk endpoints deferred**: The Jira API also has bulk property operations (`PUT/DELETE /rest/api/2/issue/properties/{propertyKey}` across multiple issues). These are not implemented — per-issue CRUD covers the primary use cases.

## Consequences

Positive:
- MCP agents and REST API clients can store and query arbitrary metadata on issues
- JQL `issue.property[key].nested.path` enables property-based search and filtering
- Import/export workflows can include property data
- No schema changes needed for new property keys — fully dynamic

Negative:
- `json_extract()` queries are not indexed — JQL property searches scan the full properties table per issue. Acceptable for an emulator but would need indexing in a production system.
- Property values are limited to 32KB (per Jira spec) and keys to 255 characters
- No property change history — unlike issue field changes, property mutations are not recorded in the changelog
