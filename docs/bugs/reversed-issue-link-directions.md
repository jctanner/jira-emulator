# Reversed Issue Link Directions

Status: Resolved

## Resolution

Fixed in two commits:

- `d99f45d` (2026-07-08): Jira REST-format import keeps each imported
  link on the side its source issue reported.
- `7050bd9` (2026-07-10): `GET /rest/api/{2,3}/issue/{key}` serializes
  `fields.issuelinks` with Jira's perspective. The stored inward issue
  shows the other issue under `outwardIssue`, and the reverse.

Tests:

- `tests/test_links.py::test_blocks_link_response_matches_real_jira_direction`
  and `test_cloners_link_response_matches_real_jira_direction`;
- the import-direction tests in `tests/test_import.py`.

Re-verified on 2026-11-14 against current `main`. A Cloners link created as
`inwardIssue=RHAISTRAT`, `outwardIssue=RHAIRFE`, which is strat-creator's
payload, renders:

- `RHAISTRAT` "clones" `RHAIRFE`, under `outwardIssue`;
- `RHAIRFE` "is cloned by" `RHAISTRAT`, under `inwardIssue`.

This holds on REST v2, REST v3, and the web UI. It matches the live Red Hat
Jira probe recorded in `strat-creator-clone-bug.md`. It also matches a real
Red Hat Jira export in breadboard:
`var/demos/dashboard-strat-arch-context-test/files/RHAIRFE-2259.json` shows
`RHAISTRAT-1859` under `inwardIssue` from the RFE.

Atlassian's public material is consistent:

- JRASERVER-34913 says clones link "from clone to original issue".
- JRACLOUD-98338 says the create request's `inwardIssue` acts as the "from"
  side.
- <https://developer.atlassian.com/cloud/jira/platform/issue-linking-model/>
  says to label a GET `outwardIssue` with the link type's `outward` text.

The `issuelink_created` and `issuelink_deleted` webhook payloads now use
Jira's `sourceIssueId`/`destinationIssueId` shape. Source is the request's
`inwardIssue`, so "source clones destination".

The rest of this note is the original report, kept for history.

## Summary

Some generated issue relationships appear to store the source and target issues in the wrong direction. This makes the REST API describe dependencies and clone relationships opposite to what the ticket content implies.

## Evidence

### Blocks relationship

`RHAI-2` is the core `diagnose` subcommand work:

- command scaffolding
- check selection and composition
- structured report output
- non-zero exit behavior for critical failures
- RBAC skip behavior

`RHAI-3` adds follow-on diagnose check categories:

- route accessibility
- TLS certificate validity
- version consistency

The current relationship says `RHAI-2` is blocked by `RHAI-3`. That is backwards: `RHAI-3` depends on the core diagnose framework from `RHAI-2`, not the other way around.

Expected relationship:

- `RHAI-2` blocks `RHAI-3`, or
- no direct blocker if both can be worked independently under `RHAISTRAT-1`

### Clone relationship

`RHAIRFE-1` is the source RFE. `RHAISTRAT-1` is the generated strategy derived from that RFE.

Current REST payload semantics show:

- On `RHAISTRAT-1`: `RHAISTRAT-1` is cloned by `RHAIRFE-1`
- On `RHAIRFE-1`: `RHAIRFE-1` clones `RHAISTRAT-1`

That is backwards for the content. The generated strategy should be the clone/derived issue.

Expected relationship:

- `RHAISTRAT-1` clones `RHAIRFE-1`, or
- `RHAIRFE-1` is cloned by `RHAISTRAT-1`

## Suspected Cause

The code that creates issue links may be assigning `inward_issue_id` and `outward_issue_id` in reverse for directional link types.

The local reproduction points specifically at Jira REST-format import handling in `src/jira_emulator/services/import_service.py`. When an imported issue contains an `issuelinks` entry with `inwardIssue`, Jira semantics mean the current source issue is the inward side and the referenced issue is the outward side. The importer currently assigns the referenced issue as inward and the source issue as outward. The `outwardIssue` branch has the mirror-image reversal.

## Local Reproduction

Environment:

- Started with `.venv/bin/honcho -f Procfile.integration start api`
- Process command from `Procfile.integration`: `uv run python -m jira_emulator serve --port $INTEGRATION_API_PORT`
- Reproduction URL: `http://127.0.0.1:19090`
- Database: isolated SQLite file under `/tmp`

### Blocks import reproduction

Import a Jira REST-style issue where `BUGLINK-1` has an `inwardIssue` link to `BUGLINK-2`:

```json
{
  "key": "BUGLINK-1",
  "fields": {
    "summary": "Blocked issue from Jira export",
    "issuelinks": [
      {
        "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
        "inwardIssue": {"key": "BUGLINK-2"}
      }
    ]
  }
}
```

Expected after import:

- `BUGLINK-1` should show `inwardIssue: BUGLINK-2`
- Meaning: `BUGLINK-1` is blocked by `BUGLINK-2`

Observed after import:

- `BUGLINK-1` shows `outwardIssue: BUGLINK-2`
- `BUGLINK-2` shows `inwardIssue: BUGLINK-1`
- Meaning is inverted to `BUGLINK-1` blocks `BUGLINK-2`

### Cloners import reproduction

Import a Jira REST-style generated strategy issue where `BUGCLONE-2` has an `outwardIssue` clone link to source `BUGCLONE-1`:

```json
{
  "key": "BUGCLONE-2",
  "fields": {
    "summary": "Generated strategy from Jira export",
    "issuelinks": [
      {
        "type": {"name": "Cloners", "inward": "is cloned by", "outward": "clones"},
        "outwardIssue": {"key": "BUGCLONE-1"}
      }
    ]
  }
}
```

Expected after import:

- `BUGCLONE-2` should show `outwardIssue: BUGCLONE-1`
- Meaning: `BUGCLONE-2` clones `BUGCLONE-1`

Observed after import:

- `BUGCLONE-2` shows `inwardIssue: BUGCLONE-1`
- `BUGCLONE-1` shows `outwardIssue: BUGCLONE-2`
- Meaning is inverted to `BUGCLONE-1` clones `BUGCLONE-2`

## Impact

The UI and REST API report misleading relationship semantics. This can invert dependency ordering for planning and make generated traceability incorrect.

## Acceptance Criteria

- Creating a directional issue link stores source and target consistently with Jira REST semantics.
- `Blocks` links render so the blocker issue uses `outwardIssue` and the blocked issue uses `inwardIssue`.
- `Cloners` links render so the cloned/derived issue is reported as cloning the source issue.
- Tests cover both sides of `Blocks` and `Cloners` relationships.
