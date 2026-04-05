# Jira "Reopen" Feature: REST API v2 and v3 Research

## Table of Contents

1. [Overview: How Reopening Works](#1-overview-how-reopening-works)
2. [Endpoints for Transitions](#2-endpoints-for-transitions)
3. [Discovering Available Transitions](#3-discovering-available-transitions)
4. [Performing the Reopen Transition](#4-performing-the-reopen-transition)
5. [Resolution Field Handling](#5-resolution-field-handling)
6. [API v2 vs v3 Differences](#6-api-v2-vs-v3-differences)
7. [Default Statuses, Transition IDs, and Status Categories](#7-default-statuses-transition-ids-and-status-categories)
8. [Real-World Examples](#8-real-world-examples)
9. [Caveats and Gotchas](#9-caveats-and-gotchas)
10. [Sources](#10-sources)

---

## 1. Overview: How Reopening Works

There is **no dedicated "reopen" API endpoint** in Jira. Reopening an issue is simply a
**regular workflow transition** that moves an issue from a "Done" status category (e.g.,
Resolved, Closed) back to a non-Done status (e.g., Reopened, Open, To Do).

In Jira's classic default workflow, "Reopen Issue" is a named transition (typically ID `3`)
that moves issues from Closed or Resolved to the "Reopened" status. In simplified/software
workflows, the transition name may be different (e.g., just "Reopen" or "To Do"), and the
ID will vary.

Key points:
- Reopening uses the exact same API endpoint as any other status transition.
- The "Reopen Issue" transition is defined in the project's workflow configuration.
- The transition must exist in the workflow and be available from the issue's current status.
- The resolution field should be cleared during reopening (but this is NOT automatic).

---

## 2. Endpoints for Transitions

Both discovering and performing transitions use the same base path, differing only by
HTTP method.

### GET - Discover Available Transitions

```
GET /rest/api/2/issue/{issueIdOrKey}/transitions
GET /rest/api/3/issue/{issueIdOrKey}/transitions
```

Optional query parameters:
- `expand=transitions.fields` - include field metadata for each transition's screen
- `transitionId={id}` - filter to a specific transition

### POST - Perform a Transition

```
POST /rest/api/2/issue/{issueIdOrKey}/transitions
POST /rest/api/3/issue/{issueIdOrKey}/transitions
```

**Important**: You must use `POST` to the `/transitions` sub-resource. The `PUT` edit-issue
endpoint (`PUT /rest/api/2/issue/{issueIdOrKey}`) does **not** support transitions -- the
transition field is silently ignored.

### Response Codes for POST

| Code | Meaning |
|------|---------|
| **204** | Transition performed successfully (no response body) |
| **400** | Invalid input (missing required fields, invalid transition ID, etc.) |
| **404** | Issue not found |
| **409** | Conflict -- another transition is already in progress for this issue |

---

## 3. Discovering Available Transitions

Before reopening an issue, you must query the available transitions to find the correct
transition ID. The transition ID for "Reopen" varies by project and workflow.

### Request

```bash
curl -u user@example.com:API_TOKEN \
  -H "Accept: application/json" \
  "https://your-domain.atlassian.net/rest/api/2/issue/PROJ-123/transitions"
```

### Response Format

```json
{
  "expand": "transitions",
  "transitions": [
    {
      "id": "3",
      "name": "Reopen Issue",
      "to": {
        "self": "https://your-domain.atlassian.net/rest/api/2/status/4",
        "description": "This issue was once resolved, but the resolution was deemed incorrect.",
        "iconUrl": "https://your-domain.atlassian.net/images/icons/statuses/reopened.png",
        "name": "Reopened",
        "id": "4",
        "statusCategory": {
          "self": "https://your-domain.atlassian.net/rest/api/2/statuscategory/4",
          "id": 4,
          "key": "indeterminate",
          "colorName": "blue",
          "name": "In Progress"
        }
      },
      "hasScreen": false,
      "isGlobal": false,
      "isInitial": false,
      "isConditional": false
    }
  ]
}
```

### Response Fields Per Transition

| Field | Description |
|-------|-------------|
| `id` | Transition ID (use this in the POST payload) |
| `name` | Display name (e.g., "Reopen Issue", "Close Issue") |
| `to` | Destination status object with `name`, `id`, `statusCategory` |
| `to.statusCategory` | Contains `key` ("new", "indeterminate", "done"), `colorName`, `name` |
| `hasScreen` | Whether the transition has an associated screen (affects field updates) |
| `isGlobal` | Whether the transition is available from any status |
| `isInitial` | Whether it's the initial (create) transition |
| `isConditional` | Whether conditions are applied |
| `fields` | (Only with `expand=transitions.fields`) Required/optional fields on screen |

### Expanded Fields Example

With `?expand=transitions.fields`:

```json
{
  "transitions": [
    {
      "id": "3",
      "name": "Reopen Issue",
      "fields": {
        "resolution": {
          "required": false,
          "schema": {
            "type": "resolution",
            "system": "resolution"
          },
          "name": "Resolution",
          "hasDefaultValue": false,
          "operations": ["set"],
          "allowedValues": [
            {"id": "1", "name": "Fixed"},
            {"id": "2", "name": "Won't Fix"},
            {"id": "3", "name": "Duplicate"}
          ]
        }
      }
    }
  ]
}
```

### Limitations

- The GET endpoint only returns transitions valid for the issue's **current** status.
  You cannot query transitions from other statuses.
- Transitions are only listed if the current user has the "Transition issues" permission.
- There is no endpoint to retrieve all possible transitions across all statuses for an
  issue type. This is a known limitation (see JRASERVER-66295).

---

## 4. Performing the Reopen Transition

### Minimal Payload

The simplest reopen payload just specifies the transition ID:

```json
{
  "transition": {
    "id": "3"
  }
}
```

### Payload with Field Updates

You can update fields during the transition using either `fields` or `update`:

```json
{
  "transition": {
    "id": "3"
  },
  "fields": {
    "resolution": null
  }
}
```

Or using the `update` block:

```json
{
  "transition": {
    "id": "3"
  },
  "update": {
    "resolution": [{"set": null}]
  }
}
```

### Payload with Comment (v2)

```json
{
  "transition": {
    "id": "3"
  },
  "update": {
    "comment": [
      {
        "add": {
          "body": "Reopening this issue because the fix didn't work."
        }
      }
    ]
  },
  "fields": {
    "resolution": null
  }
}
```

### Payload with Comment (v3 -- ADF format required)

```json
{
  "transition": {
    "id": "3"
  },
  "update": {
    "comment": [
      {
        "add": {
          "body": {
            "type": "doc",
            "version": 1,
            "content": [
              {
                "type": "paragraph",
                "content": [
                  {
                    "type": "text",
                    "text": "Reopening this issue because the fix didn't work."
                  }
                ]
              }
            ]
          }
        }
      }
    ]
  },
  "fields": {
    "resolution": null
  }
}
```

### Payload Structure Summary

```
{
  "transition": {
    "id": "<string>"           // REQUIRED - the transition ID
  },
  "fields": {                  // OPTIONAL - set field values directly
    "resolution": null | {"name": "Fixed"} | {"id": "10001"},
    "assignee": {"name": "jsmith"},
    ...
  },
  "update": {                  // OPTIONAL - field update operations
    "comment": [{"add": {"body": "..."}}],
    "resolution": [{"set": null}],
    ...
  },
  "historyMetadata": {...}     // OPTIONAL - metadata about the transition
}
```

---

## 5. Resolution Field Handling

### The Problem

When an issue is reopened, the resolution field is **NOT automatically cleared** unless
the workflow has a post-function configured to do so. This is one of the most common
sources of confusion.

Jira considers any issue with a resolution value set as a "Resolved issue" for reporting
purposes, regardless of its status. So an issue in "Reopened" status with
`resolution: "Done"` still appears as resolved in JQL filters, gadgets, and reports.

### Clearing Resolution via the API

**Option 1: Include in the transition payload**

```json
{
  "transition": {"id": "3"},
  "fields": {
    "resolution": null
  }
}
```

**Option 2: Use the update syntax**

```json
{
  "transition": {"id": "3"},
  "update": {
    "resolution": [{"set": null}]
  }
}
```

**Option 3: Separate edit after transition**

```bash
# First, transition
curl -X POST -H "Content-Type: application/json" \
  -u user:token \
  -d '{"transition":{"id":"3"}}' \
  "https://jira.example.com/rest/api/2/issue/PROJ-123/transitions"

# Then, clear resolution
curl -X PUT -H "Content-Type: application/json" \
  -u user:token \
  -d '{"fields":{"resolution":null}}' \
  "https://jira.example.com/rest/api/2/issue/PROJ-123"
```

### Important Caveats about Resolution

1. **Screen dependency**: If the transition has no screen configured, you may get:
   `"Field 'resolution' cannot be set. It is not on the appropriate screen, or unknown."`
   However, this behavior is inconsistent -- the REST API is "not expected to respect
   screens" according to Atlassian, so it may work even without a screen.

2. **Resolution date**: Clearing the resolution does NOT automatically clear the
   `resolutiondate` field. The resolution date field is not available as a field that can
   be cleared as part of a transition. This can cause JQL queries like
   `resolved IS NOT EMPTY` to still match the issue.

3. **Workflow post-functions (recommended)**: The most reliable way to clear resolution
   on reopen is to configure a "Clear Field Value" post-function on the reopen transition
   in the workflow editor. This happens server-side regardless of how the transition is
   triggered (UI, API, automation).

4. **Server/DC vs Cloud**: On Jira Server/Data Center, clearing resolution via
   `"resolution": null` in the REST API may not work reliably. The workflow post-function
   approach is strongly recommended for Server/DC.

---

## 6. API v2 vs v3 Differences

### What's the Same

- **Same endpoints**: Both versions use `/rest/api/{2|3}/issue/{key}/transitions`
- **Same HTTP methods**: GET to discover, POST to perform
- **Same response codes**: 204 on success, 400/404/409 on errors
- **Same transition logic**: The `transition.id` field, `fields`, and basic `update`
  structure are identical
- **Same field handling**: Resolution, assignee, and other non-text fields work the same

### What's Different

The **only significant difference** is how rich text content is formatted:

| Aspect | v2 | v3 |
|--------|----|----|
| Comment body | Plain text or wiki markup string | Atlassian Document Format (ADF) JSON |
| Description | Plain text or wiki markup string | ADF JSON |
| Environment field | Plain text | ADF JSON |
| Multi-line custom fields | Plain text | ADF JSON |
| Single-line custom fields | Plain string | Plain string (same) |

### Comment Format Comparison

**v2 comment during transition:**
```json
{
  "update": {
    "comment": [{"add": {"body": "Reopening this issue."}}]
  },
  "transition": {"id": "3"}
}
```

**v3 comment during transition (ADF):**
```json
{
  "update": {
    "comment": [
      {
        "add": {
          "body": {
            "type": "doc",
            "version": 1,
            "content": [
              {
                "type": "paragraph",
                "content": [
                  {"type": "text", "text": "Reopening this issue."}
                ]
              }
            ]
          }
        }
      }
    ]
  },
  "transition": {"id": "3"}
}
```

### ADF (Atlassian Document Format) Structure

ADF is a structured JSON representation of rich text. Minimum valid ADF document:

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "paragraph",
      "content": [
        {"type": "text", "text": "Your text here"}
      ]
    }
  ]
}
```

Node types include: `paragraph`, `heading`, `bulletList`, `orderedList`, `listItem`,
`codeBlock`, `blockquote`, `table`, `tableRow`, `tableHeader`, `tableCell`,
`mediaSingle`, `media`, etc.

Inline marks: `strong`, `em`, `underline`, `strike`, `code`, `link`, `textColor`,
`subsup`.

### Migration Note

When migrating from v2 to v3, the transition endpoint itself works identically. The only
change needed is formatting any comment bodies or text field updates in ADF instead of
plain text. The `transition`, `fields` (for non-text fields like resolution), and basic
structure remain unchanged.

---

## 7. Default Statuses, Transition IDs, and Status Categories

### Jira Status Categories

All statuses belong to one of three categories:

| Category | Color | Key | Meaning |
|----------|-------|-----|---------|
| To Do | Gray | `new` | Work has not started |
| In Progress | Blue | `indeterminate` | Work is underway |
| Done | Green | `done` | Work is complete |

### Default Status IDs

| Status ID | Status Name | Category |
|-----------|-------------|----------|
| 1 | Open | To Do (gray) |
| 3 | In Progress | In Progress (blue) |
| 4 | Reopened | In Progress (blue) |
| 5 | Resolved | Done (green) |
| 6 | Closed | Done (green) |

Note: In some configurations, "Reopened" is categorized as "To Do" (gray) instead of
"In Progress" (blue). The category depends on the Jira instance configuration.

### Default Workflow Transition IDs (Classic "jira" Workflow)

| Transition ID | Transition Name | From Status | To Status |
|---------------|-----------------|-------------|-----------|
| 1 | Create Issue | (initial) | Open |
| 2 | Close Issue | Multiple | Closed |
| 3 | Reopen Issue | Closed, Resolved | Reopened |
| 4 | Start Progress | Open, Reopened | In Progress |
| 5 | Resolve Issue | Open, In Progress | Resolved |

The classic default workflow has **7 transitions** total: Create Issue, Start Progress,
Stop Progress, Resolve Issue, Close Issue, Close (Resolved) Issue, and Reopen Issue.

### Simplified Software Workflow

In the simplified software workflow (used by newer Jira Software projects), the status
names and transition IDs are different:

| Typical Transition ID | Name | From | To |
|-----------------------|------|------|----|
| 11 | To Do | Any | To Do |
| 21 | In Progress | Any | In Progress |
| 31 | Done | Any | Done |
| 51 | Reopen | Done | To Do |

**Warning**: Transition IDs are NOT stable values. They are regenerated whenever a
workflow is saved. Always use the GET transitions endpoint to discover the correct IDs
at runtime.

### Default Resolution Values

| Resolution ID | Resolution Name |
|---------------|-----------------|
| 1 | Fixed |
| 2 | Won't Fix |
| 3 | Duplicate |
| 4 | Incomplete |
| 5 | Cannot Reproduce |
| 6 | Done |
| 10000 | Won't Do |

When an issue is "Unresolved", the resolution field value is `null`.

---

## 8. Real-World Examples

### Example 1: Full Reopen Workflow (v2)

```bash
# Step 1: Find the issue's current status
curl -s -u user@example.com:API_TOKEN \
  "https://your-domain.atlassian.net/rest/api/2/issue/PROJ-123?fields=status,resolution" \
  | python3 -m json.tool

# Response shows issue is "Resolved" with resolution "Done":
# {
#   "fields": {
#     "status": {"name": "Resolved", "id": "5"},
#     "resolution": {"name": "Done", "id": "6"}
#   }
# }

# Step 2: Get available transitions
curl -s -u user@example.com:API_TOKEN \
  "https://your-domain.atlassian.net/rest/api/2/issue/PROJ-123/transitions" \
  | python3 -m json.tool

# Response:
# {
#   "transitions": [
#     {"id": "3", "name": "Reopen Issue", "to": {"name": "Reopened", "id": "4"}},
#     {"id": "2", "name": "Close Issue", "to": {"name": "Closed", "id": "6"}}
#   ]
# }

# Step 3: Perform the reopen transition (clearing resolution)
curl -s -u user@example.com:API_TOKEN \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "transition": {"id": "3"},
    "fields": {"resolution": null},
    "update": {
      "comment": [
        {"add": {"body": "Reopening: the original fix did not resolve the issue."}}
      ]
    }
  }' \
  "https://your-domain.atlassian.net/rest/api/2/issue/PROJ-123/transitions"

# Response: HTTP 204 No Content (success)

# Step 4: Verify the issue was reopened
curl -s -u user@example.com:API_TOKEN \
  "https://your-domain.atlassian.net/rest/api/2/issue/PROJ-123?fields=status,resolution" \
  | python3 -m json.tool

# Expected response:
# {
#   "fields": {
#     "status": {"name": "Reopened", "id": "4"},
#     "resolution": null
#   }
# }
```

### Example 2: Reopen with ADF Comment (v3)

```bash
curl -s -u user@example.com:API_TOKEN \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "transition": {"id": "3"},
    "fields": {"resolution": null},
    "update": {
      "comment": [
        {
          "add": {
            "body": {
              "type": "doc",
              "version": 1,
              "content": [
                {
                  "type": "paragraph",
                  "content": [
                    {"type": "text", "text": "Reopening: the original fix did not resolve the issue."}
                  ]
                }
              ]
            }
          }
        }
      ]
    }
  }' \
  "https://your-domain.atlassian.net/rest/api/3/issue/PROJ-123/transitions"
```

### Example 3: Minimal Reopen (Both v2 and v3)

```bash
# Just transition, no comment, no field changes
curl -u user@example.com:API_TOKEN \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"transition": {"id": "3"}}' \
  "https://your-domain.atlassian.net/rest/api/2/issue/PROJ-123/transitions"
```

### Example 4: Python (requests library, v2)

```python
import requests
from requests.auth import HTTPBasicAuth

JIRA_URL = "https://your-domain.atlassian.net"
AUTH = HTTPBasicAuth("user@example.com", "API_TOKEN")
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

issue_key = "PROJ-123"

# Get available transitions
resp = requests.get(
    f"{JIRA_URL}/rest/api/2/issue/{issue_key}/transitions",
    auth=AUTH,
    headers=HEADERS,
)
transitions = resp.json()["transitions"]

# Find the "Reopen" transition
reopen = next((t for t in transitions if "reopen" in t["name"].lower()), None)

if reopen:
    # Perform the transition
    payload = {
        "transition": {"id": reopen["id"]},
        "fields": {"resolution": None},
        "update": {
            "comment": [{"add": {"body": "Reopening via automation."}}]
        },
    }
    resp = requests.post(
        f"{JIRA_URL}/rest/api/2/issue/{issue_key}/transitions",
        auth=AUTH,
        headers=HEADERS,
        json=payload,
    )
    assert resp.status_code == 204, f"Failed: {resp.status_code} {resp.text}"
    print(f"Issue {issue_key} reopened successfully.")
else:
    print("No 'Reopen' transition available for this issue.")
```

### Example 5: Dynamic Transition Discovery

Since transition IDs vary, here is a pattern for dynamically finding and using
the reopen transition:

```bash
# Find the reopen transition ID dynamically
REOPEN_ID=$(curl -s -u user@example.com:API_TOKEN \
  "https://your-domain.atlassian.net/rest/api/2/issue/PROJ-123/transitions" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('transitions', []):
    if 'reopen' in t['name'].lower():
        print(t['id'])
        break
")

if [ -n "$REOPEN_ID" ]; then
  curl -u user@example.com:API_TOKEN \
    -X POST \
    -H "Content-Type: application/json" \
    -d "{\"transition\":{\"id\":\"$REOPEN_ID\"},\"fields\":{\"resolution\":null}}" \
    "https://your-domain.atlassian.net/rest/api/2/issue/PROJ-123/transitions"
  echo "Reopened with transition ID: $REOPEN_ID"
else
  echo "No reopen transition found"
fi
```

---

## 9. Caveats and Gotchas

### Transition IDs are Not Stable

Transition IDs are regenerated whenever a workflow is saved. Never hardcode transition
IDs. Always discover them at runtime via the GET transitions endpoint.

### Resolution Date is Not Cleared

When you clear the `resolution` field (either via API or post-function), the
`resolutiondate` field may NOT be cleared. This is a known Jira behavior. The
`resolutiondate` field is not available as a clearable field during transitions. This
causes JQL queries like `resolved IS NOT EMPTY` to still match the reopened issue.

### Screens and Field Updates

The REST API is documented as "not expected to respect screens," meaning you can
sometimes set/clear fields that aren't on the transition screen. However, this behavior
is inconsistent. If you get a "Field cannot be set" error, the transition may need a
screen with that field added.

### Simultaneous Transitions

Jira Cloud does not support simultaneous transitions on the same issue. If multiple
transitions are requested concurrently, only one succeeds; the rest return HTTP 409
(Conflict). Implement retry logic for automation scenarios.

### Comments Require a Screen (Sometimes)

Adding a comment during a transition may only work if the transition has a screen
configured. If the transition has no screen, the comment in the `update` block may be
silently ignored. To ensure comments work, configure an empty screen on the transition
and optionally add a field validator.

### Cloud vs Server/DC Differences

- On Jira Cloud, setting `"resolution": null` during a transition generally works.
- On Jira Server/Data Center, clearing resolution via the REST API may not work
  reliably. Workflow post-functions ("Update Issue Field" set to "None") are the
  recommended approach.

### The `update` vs `fields` Block

Both `update` and `fields` can be used in the transition payload:
- `fields`: Direct field value assignment (`"resolution": null`)
- `update`: Operation-based updates (`"resolution": [{"set": null}]`)

Using both in the same request for the same field may produce unpredictable results.
Pick one approach per field.

### Resolution Set Silently by API

Jira Cloud may silently set a resolution value (e.g., "Done") when transitioning to a
Done-category status via the API, even if no resolution is specified in the payload.
This happens because Jira Cloud auto-sets resolution for Done-category transitions.
To control which resolution is set, always explicitly include it in the transition
payload.

---

## 10. Sources

### Official Atlassian Documentation

- [Jira Cloud REST API v2 - Issues](https://developer.atlassian.com/cloud/jira/platform/rest/v2/api-group-issues/)
- [Jira Cloud REST API v3 - Issues](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/)
- [Jira Cloud REST API v3 Introduction (ADF)](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/)
- [Jira Server REST API Examples](https://developer.atlassian.com/server/jira/platform/jira-rest-api-examples/)
- [Atlassian Document Format Structure](https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/)
- [Workflow Transition Properties (v3)](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-workflow-transition-properties/)
- [Change Notice: Simultaneous Transitions](https://developer.atlassian.com/cloud/jira/platform/change-notice-update-in-simultaneous-transitions-issue-api/)

### Atlassian Support / Knowledge Base

- [Clear the resolution field when an issue is reopened in Jira Cloud](https://support.atlassian.com/jira/kb/clear-the-resolution-field-when-an-issue-is-reopened-in-jira-cloud/)
- [Clear the resolution field when an issue is reopened in Jira (Server/DC)](https://support.atlassian.com/jira/kb/clear-the-resolution-field-when-an-issue-is-reopened-in-jira/)
- [Best practices on using the Resolution field in Jira Cloud](https://support.atlassian.com/jira/kb/best-practices-on-using-the-resolution-field-in-jira-cloud/)
- [How to modify your workflow to allow issues to be reopened](https://support.atlassian.com/jira/kb/how-to-modify-your-workflow-to-allow-issues-to-be-reopened/)
- [Resolution silently set by REST API call](https://support.atlassian.com/jira/kb/resolution-silently-set-by-rest-api-call/)
- [Fix Jira Resolution Issues](https://support.atlassian.com/jira/kb/fix-jira-resolution-issues/)

### Atlassian Community / Developer Forums

- [How to change the issue status by REST API](https://community.atlassian.com/forums/Jira-questions/How-to-change-the-issue-status-by-REST-API-in-JIRA/qaq-p/850658)
- [Cannot transition an issue via REST API](https://community.atlassian.com/forums/Jira-questions/Cannot-transition-an-issue-via-Rest-API/qaq-p/1194157)
- [JIRA REST API v3 - update resolution via transition with no screen](https://community.developer.atlassian.com/t/jira-rest-api-v3-can-i-update-a-resolution-via-transition-that-has-no-screen/62675)
- [How to clear or empty the Resolution field using JSON](https://community.atlassian.com/forums/Jira-questions/How-to-clear-or-empty-the-Resolution-field-using-JSON/qaq-p/2124154)
- [How to reset resolution field to "unresolved" using the REST API](https://community.atlassian.com/forums/Jira-questions/How-to-reset-resolution-field-to-quot-unresolved-using-the-REST/qaq-p/751420)
- [Addon migration from Jira Cloud REST v2 to v3](https://community.developer.atlassian.com/t/addon-migration-from-jira-cloud-rest-v2-to-v3/26986)
- [Cannot add comment when transitioning via API v3](https://community.atlassian.com/t5/Jira-questions/Cannot-add-comment-when-transitioning-an-issue-via-API-v3/qaq-p/1296894)
- [How to add comment during transition using Cloud Jira REST API](https://community.atlassian.com/forums/Jira-questions/How-to-add-comment-of-issue-during-transition-using-cloud-jira/qaq-p/2798352)

### Jira Issue Tracker

- [JRASERVER-66295: REST API endpoint to retrieve all possible transitions](https://jira.atlassian.com/browse/JRASERVER-66295)
- [JRACLOUD-75100: Clear Resolution value via REST API](https://jira.atlassian.com/browse/JRACLOUD-75100)

### Third-Party / Blog Posts

- [Understanding Jira Issue Statuses (HeroCoders)](https://www.herocoders.com/blog/understanding-jira-issue-statuses)
- [Jira Workflow Transitions (HeroCoders)](https://www.herocoders.com/blog/understanding-jira-workflow-transitions)
- [Two effective solutions for Jira Resolution field setting (Medium)](https://medium.com/@bogdan.gorka/two-effective-solutions-for-jira-resolution-field-setting-549bfd6c927b)
