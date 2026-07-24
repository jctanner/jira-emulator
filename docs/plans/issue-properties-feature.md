# Plan: Issue Properties Feature

## Goal

Add Jira issue properties (entity properties) support to the emulator — a per-issue key-value store for arbitrary JSON data, queryable via JQL.

## Context

Properties are used by Jira apps, automation rules, and MCP integrations to attach metadata to issues without creating custom fields. The emulator needed this to support clients that read/write properties and search by property values.

API spec sourced from the [Atlassian Swagger v3 spec](https://dac-static.atlassian.com/cloud/jira/platform/swagger-v3.v3.json).

## Scope

Per-issue property CRUD (v2 + v3), JQL querying, issue GET expansion, import service, and MCP tools. Bulk operations deferred.

## Acceptance Criteria

- [x] `PUT /rest/api/2/issue/{key}/properties/{propertyKey}` — set property (201 create, 200 update)
- [x] `GET /rest/api/2/issue/{key}/properties/{propertyKey}` — get property value
- [x] `GET /rest/api/2/issue/{key}/properties` — list property keys
- [x] `DELETE /rest/api/2/issue/{key}/properties/{propertyKey}` — delete property (204)
- [x] All endpoints work via `/rest/api/3/` (middleware rewrite)
- [x] `?expand=properties` on GET issue embeds property keys
- [x] JQL: `issue.property[key] = "value"` (top-level match)
- [x] JQL: `issue.property[key].nested.path = "value"` (json_extract)
- [x] JQL: `issue.property[key] IS EMPTY / IS NOT EMPTY`
- [x] Import service handles `properties` dict on issue payloads
- [x] MCP tools: getIssuePropertyKeys, getIssueProperty, setIssueProperty, deleteIssueProperty
- [x] Cascade delete when issue is deleted
- [x] All JSON value types supported (object, array, string, number, boolean, null)
- [x] 20 tests, full suite green (220 passed, 0 regressions)

## Files Created

- `src/jira_emulator/models/issue_property.py` — SQLAlchemy model
- `src/jira_emulator/routers/issue_properties.py` — REST endpoints
- `tests/test_issue_properties.py` — test suite

## Files Modified

- `src/jira_emulator/models/__init__.py` — register model
- `src/jira_emulator/models/issue.py` — add relationship
- `src/jira_emulator/app.py` — register router
- `src/jira_emulator/services/issue_service.py` — eager loading + expand
- `src/jira_emulator/routers/issues.py` — pass expand param
- `src/jira_emulator/jql/grammar.py` — PROPERTY_FIELD terminal
- `src/jira_emulator/jql/transformer.py` — property clause builder
- `src/jira_emulator/services/import_service.py` — properties import
- `mcp_servers/atlassian_jira.py` — 4 MCP tools

## Decisions

- [ADR-0001: Issue Properties Implementation](../decisions/ADR-0001-issue-properties-implementation.md)

## Status

Done
