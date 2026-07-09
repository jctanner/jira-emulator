# Duplicate Issue Links on Re-Import

## Summary

Re-importing issue data can create duplicate issue links for the same semantic relationship. This is related to, but distinct from, the reversed issue-link direction bug.

## Evidence

After rechecking `RHAI-3`, the REST payload showed two separate `Blocks` links to the same issue:

- link id `2`: `RHAI-3` -> `RHAI-2`
- link id `3`: `RHAI-3` -> `RHAI-2`

Both links have the same type and same related issue. The issue changelog also shows `RHAI-3-frontmatter.yaml` being replaced at `2026-07-08T22:13:06`, which suggests the ticket was imported again.

## Relationship to Reversed Link Direction Bug

The reversed direction bug is about incorrect mapping of Jira REST `inwardIssue` and `outwardIssue` fields into stored `IssueLink.inward_issue_id` and `IssueLink.outward_issue_id`.

This bug is about idempotency and reconciliation. Even after direction handling is fixed, re-import should not create duplicate links for relationships already present in the database.

## Suspected Cause

The import service only avoids duplicates when it finds an exact existing row with the same:

- `link_type_id`
- `inward_issue_id`
- `outward_issue_id`

That exact-match check does not handle cases where:

- an older reversed link already exists from a prior buggy import
- the same Jira link is re-imported with corrected direction
- the source export contains repeated equivalent link entries
- the Jira link `id` is available but not used for reconciliation

## Impact

Duplicate links make the UI and REST API over-report relationships. For planning relationships such as `Blocks`, duplicates can make dependency graphs look noisier or more complex than they are.

## Acceptance Criteria

- Re-importing the same Jira export does not create duplicate issue links.
- Duplicate detection handles both exact duplicate rows and semantically equivalent links produced by previous reversed imports.
- If the Jira REST link `id` is available, imports use it to support idempotent link reconciliation.
- Tests cover re-importing the same payload for `Blocks` and `Cloners` without increasing the number of links.
- Tests cover correcting or deduplicating an existing reversed link when importing the same relationship with the fixed direction.
