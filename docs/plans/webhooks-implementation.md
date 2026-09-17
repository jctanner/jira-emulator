# Jira Webhooks Implementation Plan

## Goal

Implement `references/jira-webhooks-specification.md`: both Jira-compatible
webhook management APIs, reliable outbound transmissions for the emulator's
mutation surfaces, and a simple project webhook control in the existing admin
page.

## Current State

- There is no webhook model, router, service, worker, or outbound HTTP client.
- `/rest/api/3/...` is rewritten to `/rest/api/2/...` by middleware.
- `get_db()` commits after a route handler returns, so delivery scheduled inside
  a handler could race or outlive a rollback.
- Issue field history already captures much of the changelog data needed by
  `jira:issue_updated`.
- The existing administration page at `/admin/import` already manages projects
  and users with server-rendered forms and redirect banners.
- Tables are created with SQLAlchemy `create_all`; the project has no migration
  framework.

The design therefore uses a transactional outbox written by mutation services
and a lifespan-managed delivery worker.

## Phase 1 - Models, Settings, and Serialization Boundaries

1. Add `Webhook` and `WebhookOutbox` models as specified, export them from
   `models/__init__.py`, and define useful indexes on enabled/expiry and
   outbox state/next-attempt time.
2. Add webhook settings to `config.py`, including URL policy, timeouts,
   concurrency, poll interval, and secret encryption key.
3. Add Pydantic request/response schemas in `schemas/webhook.py` for both API
   families. Keep admin and dynamic shapes separate.
4. Extract or expose shared serializers for issue, user, comment, attachment,
   link, project, and version objects. Webhook payloads must call the same code
   as REST responses.
5. Add a clock and random-delay abstraction so expiration and retry tests do
   not sleep.

Tests:

- metadata creates both tables on a fresh database;
- event arrays round-trip without duplicates;
- expiration and response timestamp formatting matches Jira format;
- secrets encrypt/decrypt and API serializers never expose them;
- startup rejects an unusable encryption-key configuration when signed
  registrations exist.

## Phase 2 - Registration Validation and Admin Webhook API

1. Create `services/webhook_service.py` with event catalogs, URL-template
   validation, JQL validation, CRUD, and response serialization.
2. Implement URL security validation as a reusable service. Validate scheme,
   userinfo, port, host resolution, literal IPs, and the private-network policy.
3. Add `routers/webhooks.py` for:

   ```http
   POST   /rest/webhooks/1.0/webhook
   GET    /rest/webhooks/1.0/webhook
   GET    /rest/webhooks/1.0/webhook/{webhookId}
   PUT    /rest/webhooks/1.0/webhook/{webhookId}
   DELETE /rest/webhooks/1.0/webhook/{webhookId}
   ```

4. Include the router in `app.py`. Ensure route definitions do not accidentally
   pass through v2/v3 rewriting.
5. Implement secret update semantics: omitted preserves, null/empty removes,
   non-empty replaces. Never return the value.

Tests:

- full create/list/get/update/delete lifecycle and status codes;
- enabled, filters, `excludeBody`, `self`, `lastUpdated`, and `isSigned` shapes;
- invalid event, filter, URL, template variable, and empty event list;
- HTTPS and port allow-list enforcement;
- private, loopback, link-local, DNS-rebinding, and redirect target rejection;
- development settings allow an HTTP/private test receiver;
- missing ids and authentication errors.

## Phase 3 - Dynamic Webhook API

Implement beneath `/rest/api/2` so middleware supplies v3 compatibility:

```http
GET    /rest/api/2/webhook
POST   /rest/api/2/webhook
DELETE /rest/api/2/webhook
PUT    /rest/api/2/webhook/refresh
GET    /rest/api/2/webhook/failed
```

Work items:

1. Associate registrations with `current_user.id`.
2. Validate each registration item independently and return ordered results.
3. Enforce the five-active-webhooks-per-user limit, including multiple items in
   one request.
4. Implement offset pagination for registrations and failure-time cursor
   pagination for failed sends.
5. Implement 30-day creation and refresh expiration. Ignore missing/unowned ids
   during delete and refresh.
6. Declare `/refresh` and `/failed` before any future id routes and verify they
   cannot be shadowed.

Tests:

- v2 and v3 paths return equivalent results;
- mixed success/error batch registration preserves order and commits successes;
- supported dynamic events and restricted JQL operators/fields;
- owner isolation for list, delete, refresh, and failures;
- limit, pagination bounds, expiration, refresh, and expired exclusion;
- delete returns `202` and refresh returns the common expiration date.

## Phase 4 - Transactional Event Capture

Build a central API with an explicit `emit_webhooks`/suppression argument rather
than adding network logic to routers. Enqueue records in the current session so
they commit or roll back with the domain mutation.

Implement matching for:

- event and enabled/expiry state;
- explicit `project_id` scope;
- JQL against the correct issue snapshot;
- updated-field and issue-property-key filters;
- dynamic owner+URL coalescing with sorted `matchedWebhookIds`.

Integrate events in this order:

1. issue create/update/delete and workflow transitions;
2. standalone and update-operation comment creation;
3. issue property set/delete;
4. attachment create/delete;
5. issue-link create/delete;
6. admin project create/delete;
7. project-version create.

For deletion routes, load and serialize all required relationships before
deleting. For updates, capture the history ids created by the current operation
so concurrent/older history entries cannot leak into the changelog. Add a
request-scoped event timestamp and trace header to the event context.

Bulk import, project configuration import, startup seed/import, reset, and
snapshot restore explicitly pass suppression. Project deletion emits one
`project_deleted` event but suppresses cascaded issue/attachment/link events.

Tests:

- one outbox record per matching admin registration;
- dynamic matches for the same owner/URL coalesce correctly;
- nonmatching project, JQL, event, field, and property filters enqueue nothing;
- disabled and expired webhooks enqueue nothing;
- issue update changelog contains exactly that request's changes;
- comment-via-update produces issue and comment events;
- delete payload snapshots remain valid after cascade deletion;
- rollback creates neither domain changes nor outbox rows;
- import/seed/reset/snapshot paths enqueue nothing.

## Phase 5 - Payloads, Templates, and Signing

1. Implement common payload construction and event-specific entity fields.
2. Reuse REST serializers and respect API-version-independent Jira webhook
   shapes.
3. Implement all documented URL substitutions needed by P0 events, with safe
   percent encoding.
4. Serialize compact canonical JSON once and persist the exact bytes/text.
5. Add `excludeBody` handling.
6. Add HMAC-SHA256 `X-Hub-Signature` over the exact transmitted bytes.
7. Preserve `X-Atlassian-Webhook-Trace` after validating its length/charset.

Tests use golden payload fixtures for each P0 event family and assert:

- common fields and event-specific objects;
- pre-delete object snapshots;
- dynamic `matchedWebhookIds` presence and admin omission;
- empty excluded body;
- URL substitution/encoding and unavailable-variable rejection;
- fixed HMAC vectors and signature stability across retries;
- user and changelog compatibility with REST output.

## Phase 6 - Delivery Worker, Retries, and Recovery

1. Add an outbound HTTP dependency appropriate for async use (prefer the
   already transitive `httpx` package as an explicit runtime dependency).
2. Implement an atomic claim/send/finalize loop. SQLite-safe claiming can use a
   short `BEGIN IMMEDIATE` transaction with a bounded claim batch.
3. Start and stop the worker in `app.py` lifespan only when webhooks are
   enabled. Do not start a real worker in unit tests unless requested by the
   fixture.
4. Apply concurrency limits with an async semaphore.
5. Implement response classification, one initial attempt plus five retries,
   jittered delays, stable identifiers, retry headers, redirect limits, and
   delivery-time address validation.
6. Recover stale claims on startup and retain failed records for the dynamic
   failed-webhook API.
7. Add bounded cleanup for delivered and old failed records.

Tests:

- successful receiver gets exact method, body, and headers after commit;
- no receiver call occurs before commit or after rollback;
- 408/409/425/429/5xx and network errors retry; terminal 4xx does not;
- retry number increments while identifier and body remain stable;
- redirect limit and each redirect's network policy are enforced;
- maximum retry exhaustion creates a failed record visible only to its owner;
- worker restart reclaims stale sends without losing the event;
- registration deletion after enqueue does not cancel the send;
- concurrency never exceeds the configured limit;
- shutdown leaves unfinished work recoverable.

## Phase 7 - Project Webhook Admin UI

1. Extend `_admin_template_context` to load projects and project-scoped admin
   webhooks with display-safe fields.
2. Add success/error banner inputs for webhook actions.
3. Add the `Project webhooks` card to `admin_import.html` with project, name,
   URL, P0 event checkboxes, secret, and enabled controls.
4. Add form handlers:

   ```http
   POST /admin/webhooks
   POST /admin/webhooks/{webhookId}/delete
   ```

5. Call the same webhook service as the REST API. Generate both the stable
   project association and `project = "KEY"` filter.
6. List existing project webhooks with signed/enabled state and deletion
   confirmation. Never repopulate or display secrets.

Tests:

- page contains the form, project choices, event choices, and existing rows;
- form creates the correct admin registration and redirects with a message;
- missing project, invalid URL/event, and policy violations redirect with an
  escaped error;
- delete removes the registration but not already queued delivery rows;
- generated JQL handles project keys safely;
- response HTML cannot expose a submitted secret or permit stored-XSS through
  webhook names/URLs.

## Phase 8 - End-to-End Compatibility and Documentation

1. Add an in-process or ephemeral local HTTP receiver integration fixture.
2. Exercise registration -> issue mutation -> signed callback -> retry/failure
   query -> refresh/delete through both API versions.
3. Verify the admin UI project flow with a real callback when insecure/private
   development flags are enabled.
4. Document settings, secure defaults, local receiver configuration, supported
   event matrix, intentional Jira differences, and operational logging in the
   README.
5. Run the full unit and integration suites plus lint/format checks.

## Recommended Implementation Order

1. Models/settings/serializers and secret handling.
2. Admin webhook CRUD API and URL policy.
3. Dynamic webhook CRUD/refresh/failure APIs.
4. Transactional matching and enqueue for issue events.
5. Payload generation, signatures, and delivery worker.
6. Remaining P0 mutation integrations.
7. Admin UI controls.
8. End-to-end tests and documentation.

This ordering makes persistence and validation independently testable, then
establishes reliable delivery for the highest-value issue events before
touching every mutation route.

## Definition of Done

- Every endpoint, transmission rule, event, security constraint, and UI flow in
  the specification has an automated test.
- All P0 event types are sent by real emulator mutations.
- Delivery is post-commit, durable, retryable, signed when configured, and
  observable through logs and the failed-webhook API.
- Secure callback policy is the default; local HTTP/private delivery requires
  explicit configuration.
- Existing Jira API, admin UI, import, and snapshot tests remain green.
