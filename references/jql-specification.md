# JQL (Jira Query Language) Specification

Collected from Atlassian documentation, March 2026.

## Sources

- https://support.atlassian.com/jira-software-cloud/docs/jql-operators/
- https://support.atlassian.com/jira-software-cloud/docs/jql-functions/
- https://www.atlassian.com/software/jira/guides/jql/cheat-sheet
- https://confluence.atlassian.com/jirasoftwareserver/advanced-searching-939938733.html

## Query Structure

```
field OPERATOR value [KEYWORD field OPERATOR value] [ORDER BY field ASC|DESC]
```

A clause consists of: **field** + **operator** + **value/function**

## Fields (System)

| Field Name | Type | Description |
|------------|------|-------------|
| `project` | project | Project key or name |
| `issuetype` / `type` | issue type | Issue type name or ID |
| `status` | status | Issue status name |
| `priority` | priority | Issue priority |
| `assignee` | user | Assigned user |
| `reporter` | user | Reporter user |
| `creator` | user | Creator user |
| `summary` | text | Issue summary/title |
| `description` | text | Issue description |
| `comment` | text | Comment body text |
| `text` | text | Searches summary + description + comments |
| `labels` | label | Issue labels |
| `component` | component | Issue components |
| `fixVersion` | version | Fix versions |
| `affectedVersion` | version | Affected versions |
| `resolution` | resolution | Resolution type |
| `created` | date | Creation date |
| `updated` | date | Last updated date |
| `resolved` | date | Resolution date |
| `due` / `duedate` | date | Due date |
| `key` / `issuekey` / `id` | issue key | Issue key (e.g., PROJ-123) |
| `parent` | issue key | Parent issue (for subtasks/epics) |
| `sprint` | sprint | Sprint name or ID |
| `epic` / `epic link` | issue key | Epic link |
| `watcher` | user | Issue watchers |
| `voter` | user | Issue voters |
| `statusCategory` | category | Status category (To Do, In Progress, Done) |

Custom fields are referenced as `cf[NNNNN]` or by their name in quotes.

## Operators

### Comparison Operators

| Operator | Syntax | Works With |
|----------|--------|-----------|
| `=` | `field = value` | All non-text fields |
| `!=` | `field != value` | All non-text fields |
| `>` | `field > value` | Dates, numbers, versions |
| `>=` | `field >= value` | Dates, numbers, versions |
| `<` | `field < value` | Dates, numbers, versions |
| `<=` | `field <= value` | Dates, numbers, versions |

### Text Operators

| Operator | Syntax | Works With |
|----------|--------|-----------|
| `~` (CONTAINS) | `field ~ "text"` | Text fields (summary, description, comment) |
| `!~` (NOT CONTAINS) | `field !~ "text"` | Text fields |

### Membership Operators

| Operator | Syntax | Description |
|----------|--------|-------------|
| `IN` | `field IN (v1, v2, v3)` | Matches any value in list |
| `NOT IN` | `field NOT IN (v1, v2)` | Excludes values in list |

### Empty/Null Operators

| Operator | Syntax | Description |
|----------|--------|-------------|
| `IS EMPTY` | `field IS EMPTY` | Field has no value |
| `IS NOT EMPTY` | `field IS NOT EMPTY` | Field has a value |
| `IS NULL` | `field IS NULL` | Alias for IS EMPTY |
| `IS NOT NULL` | `field IS NOT NULL` | Alias for IS NOT EMPTY |

### History Operators (out of scope for MVP)

| Operator | Predicates |
|----------|-----------|
| `WAS` | AFTER, BEFORE, BY, DURING, ON |
| `WAS IN` | Same as WAS |
| `WAS NOT` | Same as WAS |
| `WAS NOT IN` | Same as WAS |
| `CHANGED` | AFTER, BEFORE, BY, DURING, ON, FROM, TO |

## Keywords

| Keyword | Description |
|---------|-------------|
| `AND` | Both conditions must be true |
| `OR` | At least one condition must be true |
| `NOT` | Negates condition |
| `ORDER BY` | Sort results, default ASC |
| `ASC` | Ascending order |
| `DESC` | Descending order |
| `EMPTY` / `NULL` | Empty value constant |

## Operator Precedence

1. Parentheses `()`
2. `NOT`
3. `AND`
4. `OR`

## Functions

### Time Functions

| Function | Description |
|----------|-------------|
| `now()` | Current timestamp |
| `startOfDay()` | Start of current day |
| `endOfDay()` | End of current day |
| `startOfWeek()` | Start of current week |
| `endOfWeek()` | End of current week |
| `startOfMonth()` | Start of current month |
| `endOfMonth()` | End of current month |
| `startOfYear()` | Start of current year |
| `endOfYear()` | End of current year |

All time functions accept an optional increment: `startOfDay(-1d)`, `endOfMonth(2w)`.
Increments: `Ny` (years), `NM` (months), `Nw` (weeks), `Nd` (days), `Nh` (hours), `Nm` (minutes).

### User Functions

| Function | Description |
|----------|-------------|
| `currentUser()` | Currently logged-in user |
| `membersOf("group")` | Members of a group |

### Version Functions

| Function | Description |
|----------|-------------|
| `latestReleasedVersion(project)` | Latest released version |
| `earliestUnreleasedVersion(project)` | Earliest unreleased version |
| `releasedVersions(project)` | All released versions |
| `unreleasedVersions(project)` | All unreleased versions |

### Sprint Functions

| Function | Description |
|----------|-------------|
| `openSprints()` | Active sprints |
| `closedSprints()` | Completed sprints |
| `futureSprints()` | Not-yet-started sprints |

## Example Queries

```
project = RHAIRFE AND status = "New"
project = RHAISTRAT AND issuetype = Feature AND status != Closed
assignee = currentUser() AND status IN ("In Progress", "Review")
project = RHOAIENG AND labels = requires_architecture_review
summary ~ "architecture" OR description ~ "architecture"
created >= startOfMonth(-1M) AND project = RHAIRFE ORDER BY created DESC
priority IN (Blocker, Critical) AND fixVersion = "rhoai-3.4.EA2"
```

## Subset for Emulator MVP

The emulator should support:

**Must Have:**
- `=`, `!=`, `~`, `!~`, `IN`, `NOT IN`, `IS EMPTY`, `IS NOT EMPTY`
- `AND`, `OR`, `NOT`, `ORDER BY` (ASC/DESC)
- Parenthesized grouping
- Fields: project, issuetype/type, status, priority, assignee, reporter, summary, description, labels, component, fixVersion, key, created, updated, resolution, text
- Functions: `currentUser()`

**Should Have:**
- `>`, `>=`, `<`, `<=` (for dates)
- Functions: `now()`, `startOfDay()`, `endOfDay()`
- Fields: sprint, epic link, parent, due/duedate
- Custom field references: `cf[NNNNN]`

**Won't Have (MVP):**
- History operators: WAS, CHANGED
- Most version/sprint functions
- SLA/approval functions
