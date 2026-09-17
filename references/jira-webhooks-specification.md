# Jira Webhooks Compatibility Specification

Collected from Atlassian Jira Cloud webhook and REST API documentation and the
current emulator implementation, September 2026.

## Sources

- https://developer.atlassian.com/cloud/jira/platform/webhooks/
- https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-webhooks/
- `src/jira_emulator/app.py`
- `src/jira_emulator/database.py`
- `src/jira_emulator/routers/`
- `src/jira_emulator/services/issue_service.py`
- `src/jira_emulator/web/routes.py`

## Goal

Add useful Jira-compatible webhook registration, management, and actual HTTP
delivery to the emulator. The implementation must:

1. expose both Jira webhook REST API families;
2. emit callbacks for every supported mutation rather than merely storing
   registrations;
3. preserve callback work across process restarts and retry transient failures;
4. let an administrator configure a webhook for one project with a small form;
5. remain safe to run in developer and shared environments.

This is a compatibility target, not an implementation of Atlassian Connect or
OAuth app installation. Authentication and ownership are adapted to the
emulator's users and API tokens as described below.

## Terminology and API Families

Jira Cloud exposes two different webhook management surfaces.

### Admin webhooks

Persistent instance webhooks are managed at:

```text
/rest/webhooks/1.0/webhook
```

They have a name, description, enabled flag, optional JQL filter, optional
secret, and no automatic expiry. This is the family used by Jira's
administration screen and by the emulator's project webhook form.

### Dynamic webhooks

App-owned, expiring webhooks are managed at:

```text
/rest/api/2/webhook
/rest/api/3/webhook
```

One request can register several filters against one callback URL. Jira limits
their event set and gives them a 30-day lifetime. The emulator's existing v3 to
v2 rewrite means the implementation should register the routes once beneath
`/rest/api/2` and support both versions.

The emulator does not model Connect/OAuth applications. Dynamic webhook
ownership is therefore the authenticated user's id. A user can only list,
refresh, delete, and inspect failures for dynamic webhooks that user created.
Admin webhook routes require an authenticated user but, consistently with the
existing emulator, do not add a new global-administrator role in this feature.

## Compatibility Scope

### P0 events: fully delivered

These events correspond to mutation surfaces already implemented by the
emulator and are required in the first complete release:

| Event | Trigger |
|---|---|
| `jira:issue_created` | successful issue creation |
| `jira:issue_updated` | issue PUT, workflow transition, or issue update operations |
| `jira:issue_deleted` | successful issue deletion |
| `comment_created` | standalone comment POST or comment added through issue update operations |
| `attachment_created` | successful attachment upload; one event per attachment |
| `attachment_deleted` | successful attachment deletion |
| `issuelink_created` | successful issue-link creation |
| `issuelink_deleted` | successful issue-link deletion |
| `issue_property_set` | property create or replacement |
| `issue_property_deleted` | property deletion |
| `project_created` | project created through the admin API or UI |
| `project_deleted` | project deleted through the admin API or UI |
| `jira:version_created` | project version creation |

`jira:issue_updated` is emitted once per committed request, not once per field.
Its changelog contains all field history entries made by that operation.
Comment creation through an issue update emits both `jira:issue_updated` and
`comment_created`, matching the fact that two observable entities changed.

Import, seed, startup configuration import, snapshot restore, and database
reset do **not** emit webhooks in the initial implementation. They are bulk
administrative state-loading operations and would otherwise produce surprising
callback storms. This suppression must be explicit in service APIs and tested.

### P1 events: deliver when their mutation exists

The event catalog and registration validation also recognize the following
Jira names. Delivery is implemented alongside the corresponding mutation
surface, or immediately where that surface already exists:

- `comment_updated`, `comment_deleted`
- `project_updated`, `project_soft_deleted`, `project_restored_deleted`,
  `project_archived`, `project_restored_archived`
- `jira:version_released`, `jira:version_unreleased`,
  `jira:version_moved`, `jira:version_updated`, `jira:version_merged`,
  `jira:version_deleted`
- `issuetype_created`, `issuetype_updated`, `issuetype_deleted`
- `user_created`, `user_updated`, `user_deleted`
- `worklog_created`, `worklog_updated`, `worklog_deleted`
- `sprint_created`, `sprint_updated`, `sprint_deleted`, `sprint_started`,
  `sprint_closed`
- `board_created`, `board_updated`, `board_deleted`,
  `board_configuration_changed`
- `filter_created`, `filter_updated`, `filter_deleted`
- `app_access_to_objects_blocked`,
  `app_access_to_objects_in_container_blocked`
- `jira_expression_evaluation_failed`
- `option_voting_changed`, `option_watching_changed`,
  `option_unassigned_issues_changed`, `option_subtasks_changed`,
  `option_issuelinks_changed`, `option_timetracking_changed`, and
  `option_timetracking_provider_changed`

Registration for a recognized but non-emitting event is accepted for admin
webhooks, as Jira administration can register the full catalog. The UI labels
such events unavailable and does not offer them. Dynamic registration remains
limited to Atlassian's supported dynamic subset:

- issue created, updated, and deleted;
- comment created, updated, and deleted;
- issue property set and deleted;
- sprint created, updated, closed, deleted, and started;
- version released, unreleased, created, moved, updated, merged, and deleted.

Unknown event strings produce a validation error.

## Persistence Model

### `Webhook`

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | externally visible id |
| `kind` | string | `admin` or `dynamic` |
| `owner_user_id` | nullable FK | required for dynamic registrations |
| `project_id` | nullable FK | UI convenience scope; `SET NULL` on project deletion |
| `name` | nullable string | required for admin registrations |
| `description` | nullable text | admin metadata |
| `url` | text | callback URL template |
| `events` | JSON/text | non-empty, unique event-name array |
| `jql_filter` | nullable text | issue-related event filter |
| `field_ids_filter` | JSON/text | dynamic issue-update field filter |
| `issue_property_keys_filter` | JSON/text | dynamic property-key filter |
| `exclude_body` | boolean | admin option, default false |
| `secret_encrypted` | nullable text | never returned by an API |
| `enabled` | boolean | default true |
| `created_at` | datetime UTC | |
| `updated_at` | datetime UTC | |
| `expires_at` | nullable datetime UTC | dynamic only, creation/refresh +30 days |

Secrets must not be stored in plaintext. Add a stable application encryption
key setting and fail startup when encrypted secrets exist but the key is
missing or invalid. API responses expose only `isSigned`.

### `WebhookOutbox`

One row represents one logical callback body to one final URL:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID/string PK | value of `X-Atlassian-Webhook-Identifier` |
| `webhook_id` | nullable FK | preserve delivery if registration is later deleted |
| `url` | text | URL after variable substitution |
| `event` | string | webhook event name |
| `payload` | text | exact canonical UTF-8 JSON sent on every attempt |
| `secret_snapshot_encrypted` | nullable text | signing key as of enqueue time |
| `flow` | string | `Primary` initially; `Secondary` reserved for cascades |
| `state` | string | `pending`, `delivering`, `delivered`, `failed` |
| `attempt_count` | integer | total attempts, initially 0 |
| `next_attempt_at` | datetime UTC | worker scheduling |
| `last_status` | nullable integer | last HTTP status |
| `last_error` | nullable text | bounded diagnostic text |
| `created_at` / `delivered_at` / `failed_at` | datetime UTC | lifecycle timestamps |

Outbox rows are created in the same database transaction as the mutation. No
HTTP request is made before commit. A worker started and stopped by the FastAPI
lifespan atomically claims due rows in short transactions, sends outside the
transaction, and records the result in a new transaction. On startup it returns
stale `delivering` rows to `pending`.

Delivered rows may be removed after 24 hours. Failed rows remain queryable for
at least 72 hours. Deleting a registration does not cancel already committed
outbox rows.

## Event Capture and Matching

Mutation services call one central `enqueue_event` service with an event name,
actor, affected project, issue snapshot, changelog, and optional entity. The
service performs all matching and creates outbox records; routers do not build
payloads or send network requests.

Matching order is:

1. enabled registration containing the event;
2. dynamic registration is not expired;
3. project scope matches, when `project_id` is set;
4. JQL matches the post-mutation issue snapshot (the pre-delete snapshot for
   deletion);
5. `field_ids_filter` intersects the changed field ids for issue updates;
6. `issue_property_keys_filter` contains the affected property key.

For dynamic webhooks sharing the same owner and URL, matching registrations are
coalesced into one POST and the sorted ids are placed in
`matchedWebhookIds`. Admin registrations are delivered independently. Duplicate
registrations are intentionally allowed.

The initial JQL contract reuses the emulator's parser/evaluator and supports
the subset Atlassian permits for dynamic registration: `issueKey`, `project`,
`issuetype`, `status`, `priority`, `assignee`, and `reporter`, with `=`, `!=`,
`IN`, and `NOT IN`. Admin filters may use every clause the emulator's search
implementation supports. A filter is validated when saved; invalid filters are
rejected rather than silently never matching. Empty admin JQL matches all
issues. Non-issue event types ignore JQL and field/property filters, consistent
with Jira's sprint/version behavior.

The project admin form stores both `project_id` and the Jira-like filter
`project = "KEY"`. The foreign key provides stable internal scoping while the
filter keeps REST responses recognizable. A project key rename, if later
implemented, must update this generated filter.

## REST API: Dynamic Webhooks

All routes require the emulator's normal authentication. Jira app scopes are
not emulated.

### Register

```http
POST /rest/api/2/webhook
POST /rest/api/3/webhook
Content-Type: application/json
```

Request:

```json
{
  "url": "https://receiver.example/hooks",
  "webhooks": [
    {
      "jqlFilter": "project = DEMO",
      "events": ["jira:issue_created", "jira:issue_updated"],
      "fieldIdsFilter": ["summary", "status"],
      "issuePropertyKeysFilter": ["build"]
    }
  ]
}
```

Each element is independently validated and the `200` response preserves input
order:

```json
{
  "webhookRegistrationResult": [
    {"createdWebhookId": 1000},
    {"errors": ["The clause watchCount is unsupported"]}
  ]
}
```

A malformed top-level document or URL returns `400`. A bad filter or event in
one item is reported in that item's `errors` without rolling back valid items.
Apply Jira's limit of five active dynamic webhooks per user. The emulator does
not enforce the Connect-specific 100-per-app limit.

### List

```http
GET /rest/api/{2,3}/webhook?startAt=0&maxResults=100
```

Return only the caller's registrations, ordered by id:

```json
{
  "startAt": 0,
  "maxResults": 100,
  "total": 1,
  "isLast": true,
  "values": [
    {
      "id": 1000,
      "jqlFilter": "project = DEMO",
      "events": ["jira:issue_created"],
      "url": "https://receiver.example/hooks",
      "expirationDate": "2026-10-16T12:00:00.000+0000"
    }
  ]
}
```

Include `fieldIdsFilter` and `issuePropertyKeysFilter` only when configured.
Clamp `maxResults` to 100.

### Delete by id set

```http
DELETE /rest/api/{2,3}/webhook
{"webhookIds": [1000, 1001]}
```

Delete owned registrations and ignore missing or foreign ids. Return `202` with
an empty body.

### Extend life

```http
PUT /rest/api/{2,3}/webhook/refresh
{"webhookIds": [1000, 1001]}
```

Set recognized, owned ids to 30 days from the request time and ignore other
ids. Return `200`:

```json
{"expirationDate": "2026-10-16T12:00:00.000+0000"}
```

### Failed deliveries

```http
GET /rest/api/{2,3}/webhook/failed?maxResults=100&after=0
```

Return the caller's permanently failed dynamic deliveries oldest-first. `after`
is an epoch-millisecond failure-time cursor. Response:

```json
{
  "values": [
    {
      "id": "63bdb98c-12a8-4cbc-b708-97c62f5c9f20",
      "body": "{\"webhookEvent\":\"jira:issue_created\"}",
      "url": "https://receiver.example/hooks",
      "failureTime": 1789574400000
    }
  ],
  "maxResults": 100,
  "next": "http://jira.local/rest/api/2/webhook/failed?after=1789574400000&maxResults=100"
}
```

Omit `next` on the final page. `body` is the exact payload string.

## REST API: Admin Webhooks

### Create

```http
POST /rest/webhooks/1.0/webhook
```

Request fields are `name` (required), `description`, `url` (required), `events`
(required and non-empty), `filters`, `excludeBody` (default false), `secret`,
`enabled` (default true), and emulator-specific `allowInsecureSsl` (default
false). The latter disables certificate-chain verification for this webhook
only; HTTPS, hostname, redirect, and outbound-network policy checks still
apply. The issue JQL value is stored under Jira's key:

```json
{
  "name": "Demo integration",
  "description": "Project DEMO changes",
  "url": "https://receiver.example/hooks/{issue.key}",
  "events": ["jira:issue_created", "jira:issue_updated"],
  "filters": {"issue-related-events-section": "project = DEMO"},
  "excludeBody": false,
  "secret": "replace-me",
  "allowInsecureSsl": false
}
```

Return `201` and the stored representation, including `self`, `enabled`,
`verifySsl`, `lastUpdated` (epoch milliseconds), and `isSigned`, but never
`secret`.

### List and get

```http
GET /rest/webhooks/1.0/webhook
GET /rest/webhooks/1.0/webhook/{webhookId}
```

The collection returns a JSON array ordered by id; the member returns one
object. Unknown ids return `404` with the emulator's Jira-style error envelope.

### Update

```http
PUT /rest/webhooks/1.0/webhook/{webhookId}
```

This is a full metadata replacement using the create shape. Omitting `secret`
keeps the existing secret. Supplying `null` or `""` removes it. Return `200`
with the updated representation.

### Delete

```http
DELETE /rest/webhooks/1.0/webhook/{webhookId}
```

Return `204`; unknown ids return `404`.

## Callback Wire Contract

Callbacks are HTTP `POST` requests with the exact stored JSON bytes and:

```text
Content-Type: application/json; charset=utf-8
User-Agent: jira-emulator/<version>
X-Atlassian-Webhook-Identifier: <outbox UUID>
X-Atlassian-Webhook-Flow: Primary
X-Atlassian-Webhook-Retry: <retry number, only when greater than zero>
X-Hub-Signature: sha256=<lowercase HMAC hex, only when a secret exists>
```

`X-Hub-Signature` is HMAC-SHA256 over the exact request-body bytes. The
identifier and body remain identical across retries. If the originating REST
request supplied `X-Atlassian-Webhook-Trace`, copy its value (maximum 1024
printable ASCII characters) to the callback.

Follow at most five redirects. Treat only 2xx as success for emulator
robustness; Atlassian's guide asks receivers to return 200, but accepting all
2xx avoids retrying valid 201/202/204 acknowledgements. Retry network errors,
timeouts, `408`, `409`, `425`, `429`, and `5xx`. Other 3xx/4xx responses fail
permanently. Make one initial attempt plus five retries. Use configurable,
jittered exponential delays; production-compatible defaults are 5-15 minutes,
while tests inject zero-delay scheduling and a deterministic clock/random
source. Use a 10-second connection timeout and 30-second total timeout.

URL templates support Atlassian's documented variables when the event context
contains them, including `{issue.id}`, `{issue.key}`, `{project.id}`,
`{project.key}`, `{comment.id}`, `{attachment.id}`, `{property.key}`,
`{version.id}`, `{sprint.id}`, issue-link source/destination variables, and
modified-user variables. Percent-encode substituted values. A template that
references unavailable data is rejected at registration.

By default, callback URLs must be HTTPS, have no userinfo, and use Atlassian's
documented port allow-list. For local emulator testing,
`WEBHOOK_ALLOW_INSECURE_HTTP=true` permits HTTP. Outbound requests must resolve
and validate every redirect target against a configurable network policy.
Default-deny loopback, link-local, multicast, and private network destinations;
`WEBHOOK_ALLOW_PRIVATE_NETWORKS=true` is an explicit development escape hatch.
This validation is repeated at delivery time to limit DNS-rebinding SSRF.

### Common body fields

When `excludeBody` is false, every payload contains:

```json
{
  "timestamp": 1789574400000,
  "webhookEvent": "jira:issue_created",
  "user": {},
  "issue": {},
  "matchedWebhookIds": [1000]
}
```

- `timestamp` is event creation time in epoch milliseconds.
- `webhookEvent` is the exact registered event name.
- `user` uses the emulator's embedded Jira user shape and is present when an
  authenticated actor caused the event.
- `issue` uses `format_issue_response` with no expansions and is present for
  issue-related, comment, attachment, link, and property events. Deletion uses
  a snapshot captured before delete.
- `matchedWebhookIds` appears only for dynamic webhooks.
- `issue_event_type_name` is included for issue events (`issue_created`,
  `issue_updated`, `issue_deleted`, or `issue_generic` for transitions).

When `excludeBody` is true, send an empty body (`Content-Length: 0`) while still
setting identifier, flow, retry, trace, and signature headers. The signature is
computed over zero bytes.

### Event-specific fields

| Event family | Additional root fields |
|---|---|
| issue updated | `changelog: {id, items}`; each item has `field`, `fieldtype`, `from`, `fromString`, `to`, `toString` |
| comments | `comment`, serialized exactly like the comment REST resource |
| attachments | `attachment`, using the attachment REST shape |
| issue links | `issueLink`, plus source/destination issue context |
| issue properties | `property: {key, value}`; deletion captures the old value |
| projects | `project`, using the project REST shape |
| versions | `version`, using the version REST shape; merge also includes `mergedTo` |
| users | `user` is the modified user and `actor` is the authenticated initiator when they differ |

Payload construction must reuse existing REST serializers so callback and GET
representations do not drift. For delete events, serialize before deleting.

## Frontend Admin Control

Add a `Project webhooks` card to the existing `/admin/import` administration
page. Keep it server-rendered and consistent with the current project/user
controls.

The create form contains:

- project selector (required);
- name (defaults to `<PROJECT> webhook`);
- callback URL (required);
- event checkboxes for the P0 issue/comment/attachment/link/property events,
  defaulting to the three issue events;
- optional secret password field;
- enabled checkbox.

Submission creates one `admin` webhook with `project_id` and a generated
`project = "KEY"` JQL filter. Below the form, show existing project-scoped
webhooks with project, name, URL, events, enabled/signed state, last update, and
Delete. URLs and secrets must be HTML-escaped; secrets are never redisplayed.

UI routes:

```http
POST /admin/webhooks
POST /admin/webhooks/{webhookId}/delete
```

Both redirect to `/admin/import` with success/error query parameters, following
the existing project-maintenance pattern. REST API clients use the Jira routes,
not these form routes.

## Configuration and Operations

Add settings with conservative defaults:

| Setting | Default | Meaning |
|---|---:|---|
| `WEBHOOKS_ENABLED` | `true` | enable matching and worker |
| `WEBHOOK_SECRET_KEY` | none | application encryption key |
| `WEBHOOK_ALLOW_INSECURE_HTTP` | `false` | permit HTTP callbacks |
| `WEBHOOK_ALLOW_PRIVATE_NETWORKS` | `false` | permit private/local targets |
| `WEBHOOK_WORKER_POLL_SECONDS` | `1` | outbox poll interval |
| `WEBHOOK_MAX_CONCURRENCY` | `20` | maximum active primary sends |
| `WEBHOOK_CONNECT_TIMEOUT_SECONDS` | `10` | connection timeout |
| `WEBHOOK_TOTAL_TIMEOUT_SECONDS` | `30` | complete request timeout |

Log registration id, delivery identifier, event, hostname (not URL query
secrets), attempt, duration, and outcome. Never log webhook secrets or signature
input. Shutdown stops claiming work, allows active sends a bounded grace
period, and leaves unfinished work recoverable.

## Errors and Status Codes

- schema errors and unsupported events/filters: `400` with Jira-style
  `errorMessages`/`errors` where the upstream API does not define per-item
  errors;
- unauthenticated: existing emulator `401` behavior;
- unowned dynamic ids: treated as absent for list/delete/refresh/failures;
- unknown admin id: `404`;
- dynamic delete: `202`;
- admin delete: `204`.

## Acceptance Criteria

The feature is complete when:

1. all routes in both REST families work with the documented shapes;
2. project UI create/delete controls persist admin webhooks and never reveal a
   secret;
3. every P0 mutation emits a POST after commit with the documented body and
   headers;
4. project/JQL/event/field/property matching and dynamic coalescing are tested;
5. signatures are verified against a fixed HMAC test vector;
6. transient failures retry with a stable identifier and permanent failures
   appear in the failed-webhook endpoint;
7. restart recovery and delete-after-enqueue behavior are tested;
8. SSRF URL/redirect validation is tested for secure defaults and explicit
   development overrides;
9. existing tests remain green and disabled/suppressed webhook paths perform no
   outbound requests.

## Intentional Differences from Jira Cloud

- emulator users stand in for Connect/OAuth app ownership and scopes;
- all successful 2xx callback responses are accepted, not only 200;
- retry delay is configurable for deterministic and fast local testing;
- private and HTTP callbacks can be explicitly enabled for local development;
- registrations for recognized, currently non-emitting admin events are kept
  for forward compatibility;
- imports, seed/reset, and snapshot restoration suppress event generation.
