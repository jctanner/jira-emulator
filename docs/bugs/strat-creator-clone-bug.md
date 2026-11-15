# Strat Creator clone-link bug hypothesis

## Status: Invalidated

## Summary

This document records an investigation into whether `strat-creator` creates
`Cloners` issue links in the wrong direction when cloning an `RHAIRFE` ticket
into an `RHAISTRAT` ticket.

The hypothesis was invalidated by live Red Hat Jira testing. The public
`strat-creator` payload shape is correct for real Jira.

The emulator bug this investigation found was in GET issue-link
serialization. It was fixed in `7050bd9` (2026-07-10) and re-verified on
2026-11-14; see `reversed-issue-link-directions.md`.

## Original hypothesis

The suspected bad payload was:

```json
{
  "type": {"name": "Cloners"},
  "inwardIssue": {"key": "RHAISTRAT-..."},
  "outwardIssue": {"key": "RHAIRFE-..."}
}
```

The initial assumption was that this meant:

```text
RHAIRFE clones RHAISTRAT
```

and therefore that `strat-creator` should swap the two endpoints.

That assumption was wrong.

## Real Jira evidence

A live Red Hat Jira probe created one source `RHAIRFE` ticket and two
`RHAISTRAT` tickets, then created `Cloners` links in both possible directions.
All created tickets were clearly titled and labelled as `TESTING`, and all were
closed after evidence was captured.

Evidence artifact:

```text
real_test/artifacts/link-direction-probe-20260710-231658.json
```

Permanent note:

```text
docs/notes/real-jira-cloners-link-direction-probe.md
```

Real Jira reported the link type as:

```json
{
  "id": "10001",
  "name": "Cloners",
  "outward": "clones",
  "inward": "is cloned by"
}
```

The payload:

```json
{
  "type": {"name": "Cloners"},
  "inwardIssue": {"key": "RHAISTRAT-2213"},
  "outwardIssue": {"key": "RHAIRFE-2644"}
}
```

produced this real Jira GET behavior:

- `GET RHAISTRAT-2213` included `outwardIssue: RHAIRFE-2644`
- `GET RHAIRFE-2644` included `inwardIssue: RHAISTRAT-2213`

That renders as:

- `RHAISTRAT-2213 clones RHAIRFE-2644`
- `RHAIRFE-2644 is cloned by RHAISTRAT-2213`

This is the intended relationship for a generated strategy cloned from a
source RFE.

## Correct strat-creator behavior

For:

```text
RHAISTRAT clones RHAIRFE
```

real Jira expects:

```json
{
  "type": {"name": "Cloners"},
  "inwardIssue": {"key": "RHAISTRAT-..."},
  "outwardIssue": {"key": "RHAIRFE-..."}
}
```

The public `strat-creator` code currently does that shape by passing:

```python
create_issue_link(
    server,
    user,
    token,
    type_name="Cloners",
    inward_key=new_key,
    outward_key=args.source_key,
)
```

where `new_key` is the generated strategy and `args.source_key` is the source
RFE.

## Active emulator bug

The active bug is not that `strat-creator` creates the link incorrectly. The
active bug is that `jira-emulator` serializes issue links incorrectly when
serving `GET /rest/api/{2,3}/issue/{key}?fields=issuelinks`.

Real Jira behavior:

- if the current issue is the stored `inwardIssue`, GET returns the other issue
  under `outwardIssue`
- if the current issue is the stored `outwardIssue`, GET returns the other issue
  under `inwardIssue`

At the time of this investigation,
`src/jira_emulator/services/issue_service.py` had those response field names
reversed. Fixed in `7050bd9`.

## Acceptance criteria for the emulator fix

- Creating `Cloners` with `inwardIssue=RHAISTRAT` and
  `outwardIssue=RHAIRFE` makes `GET RHAISTRAT` return
  `outwardIssue=RHAIRFE`.
- The same link makes `GET RHAIRFE` return `inwardIssue=RHAISTRAT`.
- Creating `Blocks` with `inwardIssue=A` and `outwardIssue=B` makes `GET A`
  return `outwardIssue=B` and `GET B` return `inwardIssue=A`.
- Tests cover both directions for `Cloners` and `Blocks`.

