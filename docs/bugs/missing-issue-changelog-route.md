# Missing `GET /rest/api/2/issue/{key}/changelog`

## Status: Fixed

## Summary

The emulator served change history only embedded, through
`GET /issue/{key}?expand=changelog`. Jira also has a paged route,
`GET /issue/{key}/changelog?startAt=&maxResults=`, which returns a PageBean
(`self`, `startAt`, `maxResults`, `total`, `isLast`, `values`).
strat-creator's `strat_history.py` falls back to that route when the
embedded changelog is incomplete. Against the emulator, the fallback got a
404.

## Fix

- Added the route, with pages capped at 100 histories as in Jira. History
  formatting was pulled into
  `issue_service.format_changelog_histories`, so both forms return the same
  histories.
- Tests: `tests/test_update_ops.py`. Paged results match the embedded
  histories on REST v2 and v3, and an unknown issue returns 404.

## Known remaining behavior

History rows from one author within the same second are grouped into a
single history. Several real edits made within one second therefore appear
as one history, where Jira would show one history per edit.
