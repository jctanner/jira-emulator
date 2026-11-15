# Jira Cloud behaviour audit, 2025-01 to 2026-11 (CC-63)

Status: research complete. F1–F6 merged in #18; F7–F11 merged in #28–#31
(issues #20–#24); F12 closed until the emulator has comment update (#25).

## Purpose

Find Jira Cloud behaviour changes announced in Atlassian changelogs,
release notes, and deprecation notices that the emulator should mirror.
The window is January 2025 to mid-November 2026.

## Sources

The primary sources are:

- Jira Cloud platform changelog:
  <https://developer.atlassian.com/cloud/jira/platform/changelog/>.
  Entries are cited as `CHANGE-NNNN`, resolvable at
  `https://developer.atlassian.com/changelog/#CHANGE-NNNN`.
  - The live page renders only the newest entries. Older entries were read
    from 41 Wayback Machine snapshots taken between 2025-01 and 2026-11.
  - Some entries between about 2026-02-18 and 2026-03-19 may be missing.
- Jira Cloud REST v3 OpenAPI spec, version 1001.0.0, as published in
  November 2026:
  <https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/>.
- JQL reference pages:
  - <https://support.atlassian.com/jira-software-cloud/docs/jql-fields/>
  - <https://support.atlassian.com/jira-software-cloud/docs/jql-operators/>
  - <https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/>
  - <https://support.atlassian.com/jira-software-cloud/docs/search-syntax-for-text-fields/>
- Atlassian staff announcements:
  - RFC-61, the enhanced search API:
    <https://community.developer.atlassian.com/t/rfc-61-evolving-search-capabilities-addressing-scalability-with-a-new-enhanced-search-api/83027>
  - "work item" terminology:
    <https://community.developer.atlassian.com/t/work-is-the-new-collective-term-for-items-tracked-in-jira/88552>
  - "spaces":
    <https://community.atlassian.com/forums/Jira-Articles/Jira-Spaces-have-landed/ba-p/3117620>
- Atlassian public tracker (`jira.atlassian.com`), used only as a
  supporting reference. A JRACLOUD ticket is a filed report, not product
  policy.

`references/jira-api-deprecation-notes.md` holds earlier notes on the
search deprecation.

## Finding: the label-search "substring match" change

The suspected change does not exist.

- No changelog entry, release note, or JQL reference page says that JQL
  `labels` matching moved from exact match to substring match.
- The JQL field reference currently lists these operators for `labels`:
  - supported: `=`, `!=`, `IS`, `IS NOT`, `IN`, `NOT IN`;
  - unsupported: `~`, `!~`, `WAS*`, `CHANGED`.
- The wildcard-label request is still open as "Gathering Interest"
  (JRACLOUD-23038).
- JQL is evaluated by the server, so there is nothing in v2 vs v3 to
  separate. The reference page is not version-specific.

These real changes are the most likely sources of the memory:

1. **CHANGE-3440 (announced 2026-10-06).** On *text* fields, `=`, `IN`, and
   `NOT IN` changed from "exact match of the full field value" to "exact
   phrase search".
   - `textField = "urgent"` now matches "very urgent issue".
   - The phrase must match in order, case-insensitively, with stemming
     applied.
   - This is a substring-style change, but it applies to text fields, not
     labels.
2. **CHANGE-2913 (2025-11-30).** Labels are case-insensitive in grouped
   aggregations, for example on dashboards.
3. **`GET /rest/api/3/label` now takes `query`.** The parameter is a
   "case-insensitive prefix used to filter labels". It is present in the
   November 2026 spec; I found no changelog date.

What the emulator should do about labels:

- Keep exact, case-insensitive matching.
- Keep rejecting `~` on labels.
- Fix the empty-value semantics of `!=` and `NOT IN` (F1).

## Candidate change table

Column definitions:

- **Matches?** Whether the emulator matched Jira Cloud before this branch.
- **Pipeline impact:** the effect on strat-pipeline (strat-creator and the
  strat-workflow benchmark), rfe-autofix (`src/cli/phases.py` in
  breadboard), and fullsend (`internal/forge/jira`).
- **Pri:** P1 means fidelity bugs that change pipeline results; P2 means
  realistic client paths; P3 means additive features or work to defer.

| # | Date | Source | What changed | Affects | Matches? | Pipeline impact | Pri |
|---|---|---|---|---|---|---|---|
| 1 | Long-standing (reaffirmed by CHANGE-3001, 2026-01-28) | [jql-operators](https://support.atlassian.com/jira-software-cloud/docs/jql-operators/), [jql-fields](https://support.atlassian.com/jira-software-cloud/docs/jql-fields/), CHANGE-3001 | `!=` and `NOT IN` never match a field with no value. Users add `OR labels is EMPTY` to include unlabelled items. | JQL `labels`, `component`, `fixVersion`, `affectedVersion`, custom fields | **No.** The emulator included empty issues. | **rfe-autofix:** discovery uses `labels not in (rfe-creator-ignore, rfe-creator-autofix-rubric-pass)`. Real Jira drops unlabelled RFEs; the emulator kept them. | P1 |
| 2 | Deprecated 2024-10; CHANGE-2598 (2025-06-30) removal; progressive shutdown 2025-08 to 2025-10 | CHANGE-2046, CHANGE-2598, spec | `GET/POST /search`, `/search/id`, and `/expression/eval` are removed and return HTTP 410. | REST v2/v3 `/search` | **No**, deliberately: the emulator still serves `/search` because jira-python, the dashboard, the MCP server, and the benchmark scripts use it. | A pipeline that passes against the emulator's `/search` fails on Cloud. All in-repo Cloud paths already use `/search/jql`. | P3 (F9: opt-in 410) |
| 3 | 2024-10 onward (RFC-61, spec) | RFC-61, spec | `/search/jql` returns `{issues, nextPageToken, isLast}` with no `total`, `startAt`, or `maxResults`, on **v2 and v3**. | `/rest/api/{2,3}/search/jql` | **Partly.** v3 used cursors but still sent `total`. v2 `/search/jql` used `startAt` paging. | **fullsend** and `fetch_bugs.py` use `isLast`/`nextPageToken` and tolerate a missing `total`. Code that reads `total` passes on the emulator but breaks on Cloud. | P1 (F2) |
| 4 | Same | spec | `/search/jql` returns only `id` per issue when `fields` is omitted. | `/search/jql` | **No.** The emulator returned all fields. | A client that omits `fields` gets full issues from the emulator but only ids from Cloud. | P1 (F2) |
| 5 | Same | spec; [advanced search](https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/) | `/search/jql` rejects unbounded JQL (empty, or `ORDER BY` only) with HTTP 400. | `/search/jql` | **No.** An empty query raised a parse error, and `ORDER BY` alone was accepted. | The dashboard sends `ORDER BY updated DESC`, but only to the legacy `/search`, which is unaffected. | P1 (F2) |
| 6 | Same | spec | `expand` is a comma-separated **string** in the `/search/jql` POST body. `reconcileIssues` and `properties` were added. | `/search/jql` | **No.** The body schema ignored `expand`. | Low | P2 (F2 accepts `expand`) |
| 7 | 2024-10 onward (spec) | spec | `POST /search/approximate-count` takes `{jql}` and returns `{count}`. Bounded JQL is required. | REST v2/v3 | **No.** It returned 404. | **Observatory** Jira chat tool calls it for totals on Cloud. | P2 (F3) |
| 8 | 2026-10-06 | CHANGE-3440 | `=`, `IN`, and `NOT IN` on **text fields** become exact-phrase containment: case-insensitive, stemmed, word order kept. | JQL on free-text custom fields | **No.** The emulator compared the whole value. | None found: no pipeline queries text fields with `=`. This is the likely source of the "label substring" recollection. | P2 (F4) |
| 9 | 2025-03 onward ("work item"); 2025-10-20 onward ("space") | Developer community post; Spaces post; jql-fields page | New JQL aliases: `space`, `workType`, `workItemKey`, `workItem`, and `id` (`id` is an older alias, not new). Old names keep working; Atlassian notes some new names may not be live yet. | JQL | **No.** Unknown-field error. | None yet. It matters for agents that copy current Atlassian docs. | P2 (F5) |
| 10 | Undated, present in the Nov 2026 spec | spec | `GET /label` is paginated (`startAt`, `maxResults=1000`, `total`, `isLast`, `values`), with `query` as a case-insensitive prefix filter. | REST v2/v3 `/label` | **No.** The endpoint was missing. | Low, but the strat and rfe skills could use it for label discovery. | P3 (F6) |
| 11 | 2025-03-12 (Parent Link removed 2025-06-13; Epic Link removed 2025-09-13) | CHANGE-2401 | The Epic Link and Parent Link fields are removed from REST; use `parent`. | Issue GET/PUT, createmeta, JQL | **Mostly.** The emulator uses `parent`. Import maps legacy epic links. | None | P3 (F10: verify only) |
| 12 | 2025-03-14 | CHANGE-2398 (after CHANGE-2209) | `POST /issueLink` rejects the Epic and Sub-task link types. | `/issueLink` | **Unknown.** The emulator seeds no such types. | None | P3 (F11) |
| 13 | 2025-04-28 | CHANGE-2443 | A child comment's visibility can't be changed; it inherits from the parent. | `PUT /issue/{key}/comment/{id}` | **N/A.** The emulator has no comment PUT. | None | P3 (F12: cover when comment PUT is added) |
| 14 | 2025-12-12; enforced 2026-03-02 | CHANGE-2958, CHANGE-3003, CHANGE-3045, [rate-limiting](https://developer.atlassian.com/cloud/jira/platform/rate-limiting) | Points-based quotas. `RateLimit-Policy`/`RateLimit` headers. On 429: `Retry-After`, `X-RateLimit-Reset`, `RateLimit-Reason`. | All REST | **No** | Retry paths in the pipelines go untested. | P3 (F7: optional fault injection) |
| 15 | 2026-08-28 | CHANGE-3413 | `POST /issue/bulkfetch` allows up to 1000 issues under field and expand conditions; otherwise the limit is 100. | `/issue/bulkfetch` | **No.** The endpoint is missing. | None found | P3 (F8) |
| 16 | 2026-08-18 | CHANGE-3235 | Very large `membersOf()` expansions return an error. Comment, worklog, and history JQL searches cover only recent entries; `comment ~` covers the latest 1,000 comments per issue. | JQL | N/A at emulator scale | None | — |
| 17 | 2026-10-07; removal 2026-11-16 | CHANGE-3507 | JQL on user entity properties is rejected for voter, watcher, and creator. | JQL | N/A: not implemented | None | — |
| 18 | 2026-10-08 | CHANGE-3506, CHANGE-3103 | `/search/jql` returns 400 for invalid *custom* (Forge) JQL functions. | `/search/jql` | N/A: no Forge functions | None | — |
| 19 | 2026-11-11/12 | CHANGE-3560, CHANGE-2477 | HTTP 422 when an update would exceed a configuration limit, such as the per-space component count. | `PUT /issue`, admin APIs | **No** | None | — (deferred) |
| 20 | 2025-01-21 and 2025-04-22 | CHANGE-2278, CHANGE-2499 | In team-managed projects, `*all`/`*navigable` return only the fields associated with the project. | Issue GET, search, webhooks | N/A: the emulator models company-managed projects | None | — |
| 21 | 2025-02-08; 2025-02-22 | CHANGE-2328, CHANGE-2359 | A GET request with a body gets 403; a URL over 8192 bytes gets 413. | All REST | **No** | Long JQL in `GET /search/jql` would fail on Cloud. | — (note) |
| 22 | 2026-07-19 | CHANGE-3338, CHANGE-3339, CHANGE-3349, CHANGE-3350 | Post-function webhook payloads: `workflowId` becomes a placeholder and `workflowEntityId` is added. | Webhooks | N/A: no post-function webhooks | None | — |
| 23 | Undated | [deprecation notice](https://developer.atlassian.com/cloud/jira/platform/deprecation-notice-worklog-data-in-issue-related-events-for-webhooks/) | `worklog` objects are removed from `jira:issue_*` webhook payloads. | Webhooks | **Matches**: the emulator sends no worklog objects. | None | — |
| 24 | 2026-01-28 | CHANGE-3001 | `EMPTY` and `!=` on issue properties evaluate consistently across the navigator, the Match API, and webhooks. | JQL `issue.property[...]` | Covered by F1 for property `!=` | Low | (in F1) |

Not verified: the exact unbounded-JQL error message. Atlassian docs give
only the condition. The message used by F2, "Unbounded JQL queries are not
allowed here. Please add a search restriction to your query.", comes from
community reports of production responses.

## Proposed fixes

Each fix is one candidate issue or PR, with tests across REST v2, REST v3,
and, where relevant, MCP.

| Fix | Change | Tests | Branch state |
|---|---|---|---|
| F1 | `!=` and `NOT IN` exclude issues with no value. Covers labels, components, fix and affects versions, custom fields, and issue properties. | REST v2 and v3: an unlabelled issue is excluded from `labels != x` and `labels not in (...)` and included only with `OR labels is EMPTY`; same for components and versions. A regression test copies the rfe-autofix discovery JQL. | Implemented |
| F2 | `/search/jql` follows Cloud on v2 and v3: cursor paging with no `total`/`startAt`/`maxResults`, `fields` defaulting to `id`, unbounded JQL rejected with 400, `expand` accepted. Legacy `/search` is unchanged. | REST v2 and v3: response shape, walking all pages with `nextPageToken`, default fields, explicit fields, unbounded and empty JQL errors. Legacy `/search` still returns `total`. | Implemented |
| F3 | `POST /search/approximate-count`. | REST v2 and v3: count matches, bounded-JQL error. | Implemented |
| F4 | CHANGE-3440: on string custom fields, `=`, `IN`, and `NOT IN` match the phrase anywhere in the value, case-insensitive, on word boundaries. Select and option fields keep exact matching. | REST v2 and v3: phrase inside a longer value matches, word order is enforced, case is ignored. Select-field equality stays exact. | Implemented |
| F5 | JQL aliases `space`, `workType`, `workItemKey`, `workItem`, and `id`. | REST v2 and v3: each alias returns the same results as its canonical field. | Implemented |
| F6 | `GET /label` with `startAt`/`maxResults` and a `query` prefix filter. | REST v2 and v3: distinct sorted values, paging, case-insensitive prefix. | Implemented |
| F7 | Optional rate-limit fault injection, such as `RATE_LIMIT_FAULT=...`, returning 429 with Cloud headers. | Header names and values on a 429 | Merged (#30, issue #20) |
| F8 | `POST /issue/bulkfetch` with the 100/1000 limit rules. | Limit selection and 400 above the limit | Merged (#29, issue #21) |
| F9 | `LEGACY_SEARCH=removed` setting makes `/search` return 410 with Cloud's message. The default stays enabled. | Both settings | Merged (#31, issue #22) |
| F10 | Confirm no `Epic Link`/`Parent Link` fields are exposed through `/field` or createmeta. | `/field` assertion | Merged (#28, issue #23) |
| F11 | Reject the Epic and Sub-task link types on `POST /issueLink` if they are ever seeded. | — | Merged (#28, issue #24) |
| F12 | Child comment visibility inheritance, when comment update is implemented. | — | Closed (issue #25): no comment update endpoint yet |

Not proposed:

- **Stemming and tokenised text search** (Jira's `~` engine). The emulator
  uses substring matching, which is a long-standing, documented
  simplification. F4 uses word boundaries but does no stemming.
- **Rejecting `summary =`.** Jira supports only `~`, `!~`, and `IS` on
  `summary`, but rejecting `=` could break existing emulator users for no
  pipeline benefit. Revisit with F9 as a strict mode.

## Pipeline notes

- **rfe-autofix.** F1 changes its discovery results on the emulator so they
  match production. Unlabelled RFEs are no longer returned by
  `labels not in (...)`. If the intent is to include unlabelled RFEs, the
  query in breadboard `src/cli/phases.py:2628` must add
  `OR labels is EMPTY`; it is wrong against production today.
- **fullsend.** Its poller already sends explicit `fields` and follows
  `isLast`/`nextPageToken`, so F2 is compatible.
- **Breadboard dashboard and benchmark scripts.** They use the legacy
  `/rest/api/2/search` and read `total`. F2 does not touch that endpoint.
- **MCP server.** `searchJiraIssuesUsingJql` calls the legacy `/search` and
  is unaffected.

## Implementation notes (branch `cc-63-jira-cloud-fidelity`)

- **F1.** Negative operators on the multi-value fields (labels, components,
  fix and affects versions, sprint, custom fields, issue properties) now
  also require the field to have a value.
  - `field = EMPTY` and `field != EMPTY` map to `IS EMPTY` and
    `IS NOT EMPTY`.
  - `IN (x, EMPTY)` includes empty issues.
  - The FK-backed single-value fields (assignee, priority, and so on)
    already behaved this way through SQL `NULL` semantics.
- **F2.**
  - Removed or empty `/search/jql` parameters behave as follows:
    - `fields` defaults to `["id"]`, and the issue objects are then
      `{"id": "..."}` only.
    - `maxResults` is capped at 5000 when only `id`/`key` are requested
      and stays at 1000 otherwise. Cloud documents no fixed cap for richer
      requests, only that pages "may return fewer".
    - `isLast` comes from fetching one extra row, so it is exact on page
      boundaries.
  - The legacy `/search` handlers still nest errors as
    `{"detail": {"errorMessages": ...}}`. That predates this branch and is
    not Jira's shape. The new handlers return Jira's shape.
- **F4.**
  - The rule applies only to custom fields of type `string`, `text`,
    `textfield`, or `textarea`.
  - Matching uses whole-word phrase containment through a registered
    SQLite function, `jql_phrase_match`. There is no stemming.
  - CHANGE-3440 names `=`, `IN`, and `NOT IN` only, so `!=` is unchanged.
- **F5.** `id`, `issuekey`, `key`, `workItemKey`, and `workItem` accept a
  key, matched case-insensitively, or a numeric issue id.
- **Tests.**
  - `tests/test_jira_cloud_fidelity.py` covers every fix on REST v2 and v3.
  - `tests/integration/test_mcp.py` adds an MCP check for F1 and F5.
  - Existing tests that read `total` or full fields from `/search/jql`
    were updated to Cloud's contract.
- **Integration runner.** `make integration` could hang after the tests
  passed. Under Python 3.14, multiprocessing defaults to forkserver, so
  honcho's runners escaped the runner's process-group kill, and honcho could
  crash on teardown. Fixed separately on branch
  `fix-integration-runner-teardown`, which starts the servers directly and
  stops them by PID.
