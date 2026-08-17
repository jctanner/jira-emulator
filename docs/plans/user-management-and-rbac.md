# User Management and RBAC Plan

## Goal

Add an administrative user-management experience and then introduce role-based access control (RBAC) across the Jira Emulator.

The first deliverable is intentionally small: a read-only user manager in the existing frontend administration section that lists user identity, account status, and safe credential metadata.

## Current State

The project already has most of the underlying identity primitives:

- `User` stores username, display name, email, password hash, active state, and creation time.
- `ApiToken` stores hashed personal access tokens, a non-secret prefix, active/expiry state, and usage timestamps.
- `user_service` supports user lookup, creation, profile updates, and active-user listing.
- Jira-compatible endpoints support creating, reading, and updating users and changing passwords.
- Personal access token endpoints let the current user create, list, and revoke their own tokens.
- Authentication supports `none`, `permissive`, and `strict` modes.
- The HTML administration page already manages projects, imports, snapshots, and database reset.

Authorization is not implemented yet:

- Any authenticated REST user can call `/api/admin/*` and user mutation endpoints.
- The HTML `/admin/*` routes do not currently resolve or authorize a user.
- The user model has no role or permission assignments.
- `list_users()` excludes inactive users, which is unsuitable for an administrative directory.

## Credential Visibility Modes

The emulator should support two explicit credential-visibility modes:

- **Safe mode (default):** never return or render `password_hash`, `token_hash`, plaintext passwords, or raw token values.
- **Unsafe emulator mode (opt-in):** retain and reveal recoverable credentials to administrators for test-fixture inspection and client debugging.

Configure unsafe mode with a clearly named setting such as:

```text
ALLOW_INSECURE_CREDENTIAL_VIEW=false
```

This setting must default to `false`. Enabling it should emit a prominent startup warning and display a persistent warning banner in the administration UI.

In safe mode, **credentials** means operational metadata only:

- whether a password is configured;
- active API token count;
- token name, non-secret prefix, created time, expiry time, last-used time, and active state on a future detail view;
- password reset and token revocation actions in later phases.

Raw API tokens remain visible only once, at creation time, through the existing token-creation behavior.

### Recoverable Credential Storage

Existing bcrypt password and token hashes cannot be converted back into their original plaintext values. Unsafe mode therefore requires storing a separate recoverable value when a password or token is created or changed.

For emulator simplicity, add nullable fields dedicated to unsafe storage, for example `password_plaintext` on `User` and `token_plaintext` on `ApiToken`. They must only be populated while `ALLOW_INSECURE_CREDENTIAL_VIEW=true`; safe mode continues to store hashes only. Credentials created before unsafe mode is enabled remain unavailable and should render as `Not retained` rather than presenting the hash as if it were the credential.

Operational rules:

- never confuse a bcrypt hash with a usable credential or label hashes as passwords/tokens;
- never place plaintext credentials in logs, exception messages, URLs, query parameters, or normal list-page HTML;
- reveal values only on an explicit administrator action or dedicated detail view;
- mark revealed values as emulator-only test data and make them easy to copy;
- clear retained plaintext when a credential is reset, revoked, or deleted;
- switching the setting off immediately disables reveal endpoints and UI controls, although retained database values remain until explicitly scrubbed;
- provide an administrative scrub operation to permanently clear all retained plaintext credentials;
- document that database snapshots and backups created while unsafe mode is enabled contain plaintext secrets.

An optional stricter setting can disable authorization checks independently for isolated test environments, for example:

```text
DISABLE_RBAC=false
```

This must also default to `false`, emit a startup/UI warning when enabled, and must not implicitly enable plaintext credential retention or display. Credential visibility and authorization bypass are separate controls.

## Phase 1 - Read-Only User Manager

Add a **User Management** card to `src/jira_emulator/web/templates/admin_import.html` using the existing admin page and table styles.

Display every user, including inactive accounts, with these columns:

- username;
- display name;
- email address;
- account status (`Active` or `Inactive`);
- credential status (`Password set` or `No password`);
- active API token count;
- created timestamp.

Implementation:

- Extend `_admin_template_context()` in `src/jira_emulator/web/routes.py` with a query for all users ordered case-insensitively by username.
- Aggregate active API token counts in the same query or a bounded companion query; avoid one query per user.
- Convert database rows to a presentation-specific dictionary rather than passing password or token models to the template.
- Render missing email addresses as an em dash and timestamps in a consistent UTC format.
- Keep the first version server-rendered; a new JSON endpoint is unnecessary for a page that already receives a shared server-side context.
- Add a user count to the card heading or supporting text so an empty and populated directory are obvious.

### Phase 1 Acceptance Criteria

- [x] `GET /admin/import` includes a User Management section.
- [x] Active and inactive users are both listed.
- [x] Username, display name, email, status, password presence, active token count, and creation time are shown.
- [x] Users are sorted deterministically by username, case-insensitively.
- [x] The page performs a bounded number of queries as the user count grows.
- [x] In safe mode, no password hash, token hash, plaintext password, or raw token is present in HTML or template context.
- [ ] In unsafe mode, the list still shows credential status rather than embedding every plaintext credential in the page.
- [x] The page has a useful empty state when no users exist.
- [x] Existing project, import, snapshot, and reset sections continue to work.

### Phase 1 Tests

Add `tests/test_admin_users.py` covering:

- seeded admin user appears in the admin page;
- a user with name and email renders correctly;
- an inactive user remains visible and is labeled inactive;
- password presence is reported without exposing the stored hash;
- active token counts exclude revoked tokens;
- sensitive credential values do not appear in the response body in safe mode;
- enabling unsafe mode does not automatically embed plaintext credentials in the directory response;
- users appear in deterministic order.

## Phase 2 - Basic User Lifecycle Actions

**Status: Implemented.** Unsafe plaintext credential retention/reveal remains separate follow-on work.

After the directory is established, add narrowly scoped actions:

- create a user with username, display name, email, and initial password;
- edit display name and email;
- activate or deactivate an account;
- set or reset a password without displaying the existing credential;
- view credential metadata and revoke a user's API tokens.

When unsafe emulator mode is enabled, the user detail view may additionally reveal retained plaintext passwords and token values. Each reveal should be explicit rather than included in the main directory, so routine page loads and screenshots do not disclose every credential.

Use dedicated service methods for validation and state changes so HTML form handlers and REST endpoints share behavior. Enforce unique usernames and normalized, unique non-empty emails. Prefer deactivation over deletion because issues, comments, and history may reference users.

Safety rules:

- prevent an administrator from deactivating the last active administrator;
- invalidate or reject authentication for inactive users;
- decide explicitly whether deactivation also revokes active tokens (recommended: revoke them transactionally);
- use POST/redirect/GET for HTML mutations and display success/error banners;
- add CSRF protection before enabling browser-based destructive actions when cookie sessions are supported.

Add tests for both credential modes:

- safe mode never stores or reveals plaintext;
- unsafe mode retains newly created and reset passwords/tokens;
- credentials created before unsafe mode was enabled show `Not retained`;
- disabling unsafe mode hides retained values immediately;
- the scrub operation clears retained values without invalidating their hashes;
- revoked tokens can no longer be revealed;
- startup and UI warnings appear when insecure controls are enabled.

## Phase 3 - RBAC Foundation

Start with two global roles:

- `admin`: may access administration UI/API and manage users, credentials, projects, imports, snapshots, and resets;
- `user`: may use ordinary Jira-compatible issue and project features.

Recommended model:

- add a `roles` table;
- add a `user_roles` association table with uniqueness on `(user_id, role_id)`;
- seed `admin` and `user` roles;
- assign the configured default admin account the `admin` role;
- assign newly auto-created users the `user` role only.

Introduce reusable dependencies such as `require_authenticated_user` and `require_role("admin")`. Apply the admin requirement consistently to both `/api/admin/*` and HTML `/admin/*` routes, plus administrative user mutations.

Because this project currently relies on SQLAlchemy `create_all()` rather than a migration framework, adding RBAC tables is additive. Any new column on an existing table will need an explicit schema-upgrade strategy for persistent SQLite databases; adding separate role tables avoids that problem initially.

### Authentication Compatibility

- In `strict` mode, enforce authentication and RBAC normally.
- In `none` mode, resolve the configured default user and its roles.
- In `permissive` mode, continue compatibility-oriented user discovery, but do not grant `admin` merely because a caller supplies the username `admin`.
- Reject inactive users for Basic, Bearer, and cookie-session authentication.
- If `DISABLE_RBAC=true`, bypass role checks but continue resolving a current user for attribution and auditing.
- `DISABLE_RBAC` must not weaken password/token validation in `strict` authentication mode; bypassing authentication would require a separate, already-supported choice such as `AUTH_MODE=none`.

## Phase 4 - Permission Expansion

Only add finer-grained permissions when real use cases require them. Likely candidates are:

- `users:read`, `users:write`, and `credentials:write`;
- `projects:admin`;
- `imports:run`;
- `snapshots:manage`;
- `system:reset`.

Keep roles as named bundles of permissions. Avoid project-scoped role assignments until global roles are working and tested, since project membership introduces a second authorization dimension and substantially more UI/API complexity.

## Out of Scope for the Initial Delivery

- revealing credentials in the Phase 1 list view;
- recovering credentials that were stored only as one-way hashes;
- ever displaying password hashes or token hashes as usable credentials;
- hard-deleting users;
- project-scoped roles or groups;
- external identity providers, SSO, LDAP, or OAuth provisioning;
- password complexity, recovery email, and account lockout policy;
- a standalone single-page admin application.

## Implementation Order

1. Add the read-only user query and safe presentation model to the shared admin context.
2. Render the User Management table and empty state.
3. Add focused HTML and credential-redaction tests.
4. Add the opt-in unsafe credential-retention configuration, warning surfaces, reveal detail, and scrub operation.
5. Add lifecycle service methods and administrator actions.
6. Add role tables, seeded assignments, and authorization dependencies.
7. Protect every HTML and REST administrative route, with the explicit `DISABLE_RBAC` emulator override.
8. Audit inactive-user handling across Basic, Bearer, and session authentication.
9. Expand to permission bundles only when global admin/user roles prove insufficient.

## Verification

Run focused tests during the first delivery:

```bash
uv run pytest tests/test_admin_users.py tests/test_admin_projects.py tests/test_auth.py tests/test_tokens.py
```

Run lint and the complete suite before considering a phase complete:

```bash
uv run ruff check src tests
uv run pytest
```

## Status

Phases 1 and 2 implemented. Unsafe credential reveal and the RBAC phases remain a roadmap.
