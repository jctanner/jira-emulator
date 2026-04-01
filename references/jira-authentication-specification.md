# Jira Authentication — Complete Specification

Collected from Atlassian developer documentation and support resources, March 2026.

## Sources

- https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/
- https://developer.atlassian.com/server/jira/platform/basic-authentication/
- https://developer.atlassian.com/server/jira/platform/personal-access-token/
- https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html
- https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/
- https://support.atlassian.com/jira/kb/how-to-create-a-user-on-jira-using-rest-api/
- https://developer.atlassian.com/server/jira/platform/rest/v10000/api-group-password/
- https://developer.atlassian.com/server/jira/platform/cookie-based-authentication/

---

## 1. Authentication Methods Overview

Jira supports multiple authentication methods depending on Cloud vs. Server/Data Center:

| Method | Cloud | Server/DC | Header Format |
|--------|-------|-----------|---------------|
| Basic Auth (email + API token) | Yes | No | `Authorization: Basic base64(email:api_token)` |
| Basic Auth (username + password) | No | Yes | `Authorization: Basic base64(username:password)` |
| Bearer Token (PAT) | No | Yes | `Authorization: Bearer <PAT>` |
| Cookie/Session (deprecated) | Deprecated | Yes | `Cookie: JSESSIONID=<value>` |

**Key distinction:** Jira Cloud uses `email:api_token` with Basic auth. Jira Server/DC uses `username:password` with Basic auth, or PATs with Bearer auth.

---

## 2. Basic Authentication (Server/Data Center)

### How It Works

1. Construct credential string: `username:password`
2. Base64-encode the string
3. Set header: `Authorization: Basic <encoded_string>`

### Example

Credentials `fred:fred` → Base64 `ZnJlZDpmcmVk`:

```bash
curl -H "Authorization: Basic ZnJlZDpmcmVk" \
  -H "Content-Type: application/json" \
  http://localhost:8080/rest/api/2/issue/KEY-1
```

Or using the `-u` shorthand:
```bash
curl -u fred:fred http://localhost:8080/rest/api/2/issue/KEY-1
```

### Error Handling

- **401 Unauthorized**: Invalid credentials
- **403 Forbidden**: Valid credentials but insufficient permissions
- **CAPTCHA trigger**: After several consecutive failed login attempts, Jira triggers a CAPTCHA
  - Response includes header: `X-Seraph-LoginReason: AUTHENTICATION_DENIED`
  - REST API authentication is blocked until CAPTCHA is resolved via web UI
- **Important**: Jira permits anonymous access by default and does NOT issue authentication challenges — clients must send the `Authorization` header proactively

### Security Notes

- Basic auth sends credentials on every request (can be cached by browser)
- Not recommended for production integrations; use PATs or OAuth instead
- Username/password validated against Jira's internal user directory (or connected LDAP)

---

## 3. Basic Authentication with API Tokens (Cloud)

### How It Works

1. Generate an API token at https://id.atlassian.com/manage-profile/security/api-tokens
2. Construct credential string: `email:api_token`
3. Base64-encode the string
4. Set header: `Authorization: Basic <encoded_string>`

### Example

```bash
curl -H "Authorization: Basic $(echo -n 'user@example.com:api_token_string' | base64)" \
  -H "Content-Type: application/json" \
  https://your-domain.atlassian.net/rest/api/2/issue/QA-31
```

### API Token Properties

- **Expiration**: Default 1 year; configurable 1-365 days
- **Scopes** (optional): Restrict token to specific actions (view, write, delete)
- **Variable length**: Tokens use variable-length format
- Cannot be recovered after creation — must be stored at creation time

### Important: Bearer Auth Does NOT Work on Cloud

PATs sent as `Authorization: Bearer <token>` are **rejected** on Jira Cloud with `403 Forbidden`. Cloud only accepts API tokens via Basic auth (email:token).

---

## 4. Personal Access Tokens (Server/Data Center)

Available since Jira 8.14, Confluence 7.9.

### Using a PAT for Authentication

Pass the PAT as a Bearer token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer <PAT>" \
  https://jira.example.com/rest/api/2/myself
```

The "Bearer" prefix is mandatory. The server identifies the user from the token — no username is needed in the header.

### Token Structure

The token consists of two parts:
- **ID**: 12-digit number representing the user
- **Secret**: 20 bits of random data

The ID + `:` + secret are concatenated and Base64-encoded to produce the final token string. Once generated, the raw token cannot be retrieved from the server.

### REST API Endpoints for PAT Management

#### Create a PAT

```
POST /rest/pat/latest/tokens
Content-Type: application/json
Authorization: Basic <base64(username:password)>

{
  "name": "tokenName",
  "expirationDuration": 90
}
```

**Request fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Label for the token |
| `expirationDuration` | integer | No | Validity in days. If omitted, token never expires (if allowed by admin) |

**Response 200:**
```json
{
  "id": "123456789012",
  "name": "tokenName",
  "createdAt": "2026-01-15T10:30:00.000+0000",
  "expiringAt": "2026-04-15T10:30:00.000+0000",
  "rawToken": "MTIzNDU2Nzg5MDEyOnNlY3JldGRhdGFoZXJl"
}
```

The `rawToken` is only returned at creation time and cannot be retrieved later.

**Authentication**: Must authenticate as the user who will own the token (Basic auth with username:password, or existing Bearer token).

**Limits**:
- Max 10 tokens per user (configurable via `atlassian.pats.max.tokens.per.user` property)
- Non-expiring tokens can be disabled via `atlassian.pats.eternal.tokens.enabled` property (true by default)

#### List PATs

```
GET /rest/pat/latest/tokens
Authorization: Bearer <PAT> | Basic <base64(username:password)>
```

Returns all tokens for the authenticated user. Token secrets are NOT included in the response.

#### Revoke a PAT

```
DELETE /rest/pat/latest/tokens/{tokenId}
Authorization: Bearer <PAT> | Basic <base64(username:password)>
```

Revokes the specified token. It can no longer be used for authentication.

### Admin Management

Administrators can:
- View all tokens in the system (`Administration > System > Personal access tokens`)
- Filter by author, creation date, expiration date, last used
- Bulk revoke tokens
- Set system-wide policies (max tokens per user, allow/disallow non-expiring tokens)

---

## 5. Cookie/Session Authentication (Server/Data Center)

**Note:** Deprecated on Jira Cloud. Still works on Server/Data Center but PATs are recommended.

### Login Endpoint

```
POST /rest/auth/1/session
Content-Type: application/json

{
  "username": "fred",
  "password": "fred"
}
```

**Response 200:**
```json
{
  "session": {
    "name": "JSESSIONID",
    "value": "42424424242342434234.node1"
  },
  "loginInfo": {
    "failedLoginCount": 6,
    "loginCount": 356,
    "lastFailedLoginTime": "2026-01-14T09:00:00.000+0000",
    "previousLoginTime": "2026-01-15T08:00:00.000+0000"
  }
}
```

The server also sets cookies via `Set-Cookie` headers:
- `JSESSIONID` — primary session cookie
- `atlassian.xsrf.token` — CSRF protection token
- `studio.crowd.tokenkey` — Crowd SSO token (if applicable)

### Using the Session Cookie

```bash
curl -b "JSESSIONID=42424424242342434234.node1" \
  -H "Content-Type: application/json" \
  http://localhost:8080/rest/api/2/issue/KEY-1
```

**Important:** In some configurations, all returned cookies (not just JSESSIONID) must be included in subsequent requests.

### Logout

```
DELETE /rest/auth/1/session
```

### Get Current Session

```
GET /rest/auth/1/session
```

Returns the current session info if authenticated, or 401 if not.

---

## 6. User Management REST API (Server/Data Center)

### Create User

```
POST /rest/api/2/user
Content-Type: application/json

{
  "name": "jdoe",
  "password": "s3cureP@ss",
  "emailAddress": "jdoe@example.com",
  "displayName": "John Doe",
  "applicationKeys": ["jira-software"]
}
```

**Request fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Username (login name) |
| `password` | string | Yes | Initial password |
| `emailAddress` | string | Yes | Email address |
| `displayName` | string | Yes | Full display name |
| `applicationKeys` | string[] | No | Product licenses to assign |

**Response 201:** Returns the created user object.

### Get User

```
GET /rest/api/2/user?username=jdoe
```

**Response 200:**
```json
{
  "self": "http://localhost:8080/rest/api/2/user?username=jdoe",
  "key": "jdoe",
  "name": "jdoe",
  "emailAddress": "jdoe@example.com",
  "displayName": "John Doe",
  "active": true,
  "timeZone": "America/New_York"
}
```

### Update User

```
PUT /rest/api/2/user?username=jdoe
Content-Type: application/json

{
  "emailAddress": "john.doe@example.com",
  "displayName": "John M. Doe"
}
```

Only `emailAddress` and `displayName` can be changed. Fields omitted from the request remain unchanged.

### Change Own Password

```
PUT /rest/api/2/myself/password
Content-Type: application/json
Authorization: Basic <base64(username:current_password)>

{
  "currentPassword": "oldP@ss",
  "password": "newP@ss"
}
```

Available to any authenticated user for their own account (no admin required).

### Change Another User's Password (Admin Only)

```
PUT /rest/api/2/user/password?username=jdoe
Content-Type: application/json
Authorization: Basic <base64(admin_username:admin_password)>

{
  "password": "newP@ss"
}
```

Requires Jira admin permissions. The `currentPassword` field is NOT required when an admin changes another user's password.

### Important: Cloud Differences

On Jira Cloud, the password management endpoints do NOT exist — passwords are managed by Atlassian account (SSO). User creation on Cloud uses a different format and does not accept `name` or `password` fields.

---

## 7. `/rest/api/2/myself` Endpoint

Used by clients to validate authentication and get current user info.

```
GET /rest/api/2/myself
Authorization: Basic <credentials> | Bearer <PAT>
```

**Response 200:**
```json
{
  "self": "http://localhost:8080/rest/api/2/myself",
  "key": "admin",
  "name": "admin",
  "emailAddress": "admin@example.com",
  "displayName": "Admin User",
  "active": true,
  "timeZone": "UTC",
  "groups": {
    "size": 2,
    "items": []
  }
}
```

**Response 401:** If credentials are invalid (strict mode).

---

## 8. Emulator Implementation Notes

For the Jira emulator, implement the following authentication features:

### Auth Modes

| Mode | Behavior |
|------|----------|
| `permissive` (default) | Accept any valid auth header; extract username; auto-create users |
| `strict` | Validate Basic auth against stored password hashes; validate Bearer tokens against `api_tokens` table |
| `none` | No auth required; all requests use default anonymous user |

### Database Schema Additions for Auth

```sql
-- Add password_hash column to users table
ALTER TABLE users ADD COLUMN password_hash TEXT;

-- API tokens / Personal Access Tokens table
CREATE TABLE api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    name TEXT NOT NULL,                    -- Token label (e.g., "CI pipeline token")
    token_hash TEXT NOT NULL,             -- bcrypt/argon2 hash of the raw token
    token_prefix TEXT,                    -- First 8 chars for identification
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,                 -- NULL = never expires
    last_used_at TIMESTAMP,
    active BOOLEAN DEFAULT TRUE,
    UNIQUE(user_id, name)
);
```

### Auth Endpoints to Implement

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/rest/api/2/myself` | Get current authenticated user |
| `POST` | `/rest/api/2/user` | Create user (with password) |
| `GET` | `/rest/api/2/user?username=X` | Get user details |
| `PUT` | `/rest/api/2/user?username=X` | Update user (email, displayName) |
| `PUT` | `/rest/api/2/myself/password` | Change own password |
| `PUT` | `/rest/api/2/user/password?username=X` | Admin: change user's password |
| `POST` | `/rest/pat/latest/tokens` | Create a personal access token |
| `GET` | `/rest/pat/latest/tokens` | List own tokens |
| `DELETE` | `/rest/pat/latest/tokens/{tokenId}` | Revoke a token |

### Password Hashing

Use `bcrypt` (via the `passlib` or `bcrypt` Python package) for password storage:
- Never store plaintext passwords
- Hash on user creation and password change
- Compare hashes on Basic auth validation in strict mode

### Token Generation

For PATs:
1. Generate a cryptographically secure random token (e.g., `secrets.token_urlsafe(32)`)
2. Store the bcrypt hash of the token in `api_tokens.token_hash`
3. Store first 8 characters in `api_tokens.token_prefix` for display/identification
4. Return the raw token to the user once at creation time
5. On Bearer auth, hash the provided token and compare against stored hashes

### Auth Flow (Strict Mode)

```
Request arrives with Authorization header
├── Basic auth header?
│   ├── Decode base64 → username:password (or email:token)
│   ├── Look up user by username (or email)
│   ├── Verify password hash matches
│   ├── Match? → Set request.state.user, proceed
│   └── No match? → 401 Unauthorized
├── Bearer token header?
│   ├── Look up token by checking hash against api_tokens table
│   ├── Check token is active and not expired
│   ├── Match? → Set request.state.user (from token's user_id), proceed
│   └── No match? → 401 Unauthorized
└── No auth header?
    └── 401 Unauthorized
```

### Auth Flow (Permissive Mode)

```
Request arrives with Authorization header
├── Basic auth header?
│   ├── Decode base64 → username:password
│   ├── Look up or auto-create user by username
│   └── Set request.state.user, proceed (password NOT checked)
├── Bearer token header?
│   ├── Look up token in api_tokens table
│   ├── Match? → Set request.state.user from token owner
│   └── No match? → Use default user, proceed anyway
└── No auth header?
    └── Use default user, proceed
```
