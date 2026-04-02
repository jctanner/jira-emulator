You are implementing a lightweight Jira MCP server for a project that needs to
provide Atlassian-compatible MCP tools to Claude Agent SDK sessions. The server
must match the tool names and behavior of the official Atlassian remote MCP
server (https://mcp.atlassian.com) so that existing skills designed for that
server work without modification.

## Context

This server will be launched as a subprocess by the Claude Agent SDK via
ClaudeAgentOptions.mcp_servers, registered under the name "atlassian". The
consuming skills reference tools as mcp__atlassian__<toolName>.

The Jira instance is a local emulator running at the URL specified by the
JIRA_SERVER environment variable. It exposes a standard Jira REST API
(v2 and/or v3). Authentication uses Basic Auth with JIRA_USER and JIRA_TOKEN.

## Requirements

### Framework

Use the FastMCP Python framework (pip package: `mcp`). The server runs over
stdio transport (the SDK launches it as a subprocess). Minimal example:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("atlassian")

@mcp.tool()
def getJiraIssue(issueIdOrKey: str) -> dict:
    ...

mcp.run(transport="stdio")
```

### Tools to implement

Implement exactly these tools with exactly these names (camelCase). The names
MUST match — consuming skills use these exact strings.

1. **getJiraIssue**
   - Input: `issueIdOrKey` (string, required) — Jira issue key like "RHAIRFE-9"
   - Behavior: GET /rest/api/2/issue/{issueIdOrKey}
   - Return: The full issue JSON (key, fields.summary, fields.description,
     fields.priority, fields.status, fields.labels, fields.issuetype,
     fields.comment, etc.)
   - The description field may be either a string (Jira Server wiki markup),
     a rendered HTML string, or an ADF document (JSON object). Return it as-is
     from the API.

2. **searchJiraIssuesUsingJql**
   - Input: `jql` (string, required), `maxResults` (int, optional, default 50),
     `fields` (list[str], optional)
   - Behavior: POST /rest/api/2/search with body {"jql": ..., "maxResults": ..., "fields": ...}
     (POST search is more reliable than GET for complex JQL)
   - Return: The search response (issues array, total, startAt, maxResults)

3. **createJiraIssue**
   - Input: `projectKey` (string, required), `issueTypeName` (string, required),
     `summary` (string, required), `description` (string, optional),
     `priority` (string, optional), `labels` (list[str], optional),
     `additionalFields` (dict, optional) — extra fields to merge into the
     fields object
   - Behavior: POST /rest/api/2/issue with the constructed fields payload
   - Return: The created issue response (id, key, self)

4. **editJiraIssue**
   - Input: `issueIdOrKey` (string, required), `fields` (dict, required) —
     fields to update (e.g. {"summary": "new title", "description": "..."})
   - Behavior: PUT /rest/api/2/issue/{issueIdOrKey} with body {"fields": ...}
   - Return: Success confirmation or the updated issue

5. **addCommentToJiraIssue**
   - Input: `issueIdOrKey` (string, required), `body` (string, required) —
     comment text (plain text or ADF JSON string)
   - Behavior: POST /rest/api/2/issue/{issueIdOrKey}/comment with {"body": body}
   - Return: The created comment

6. **getTransitionsForJiraIssue**
   - Input: `issueIdOrKey` (string, required)
   - Behavior: GET /rest/api/2/issue/{issueIdOrKey}/transitions
   - Return: Available transitions array

7. **transitionJiraIssue**
   - Input: `issueIdOrKey` (string, required), `transitionId` (string, required),
     `fields` (dict, optional)
   - Behavior: POST /rest/api/2/issue/{issueIdOrKey}/transitions with
     {"transition": {"id": transitionId}, "fields": ...}
   - Return: Success confirmation

### API version

Use Jira REST API **v2** (/rest/api/2/) since this targets a local emulator
that may not support v3/ADF. If the emulator returns plain text or wiki markup
for description fields, that's fine — return as-is. The consuming skills handle
both formats.

### Authentication

Read credentials from environment variables:
- JIRA_SERVER — base URL (e.g. http://localhost:8080)
- JIRA_USER — username or email
- JIRA_TOKEN — API token or password

Use HTTP Basic Auth: base64(JIRA_USER:JIRA_TOKEN) in the Authorization header.

Fail fast at startup if any of the three env vars are missing.

### Error handling

- Return structured error messages on HTTP errors (include status code and
  response body from Jira)
- Handle connection errors gracefully (the emulator may not be running)
- Use urllib.request (stdlib) for HTTP — avoid adding requests as a dependency

### Project structure

Create the server as a single Python module at:
  mcp_servers/atlassian_jira.py

It should be runnable as:
  python mcp_servers/atlassian_jira.py

The only dependency beyond stdlib is `mcp` (the FastMCP framework).
Add `mcp>=1.2.0` to the project's pyproject.toml dependencies if not
already present.

### What NOT to do

- Do not implement Confluence tools — only Jira is needed
- Do not implement OAuth or any auth besides Basic Auth
- Do not add caching, rate limiting, or retry logic — keep it simple
- Do not modify any files outside of mcp_servers/ and pyproject.toml
- Do not add tools beyond the 7 listed above

### Testing

After implementation, verify the server starts and lists its tools:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python mcp_servers/atlassian_jira.py
```

This should return a JSON-RPC response listing all 7 tools with their
input schemas.
