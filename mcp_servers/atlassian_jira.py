"""Atlassian-compatible Jira MCP server for Claude Agent SDK.

Provides 7 tools matching the official Atlassian remote MCP server tool names.
Connects to a local Jira emulator via REST API v2 with Basic Auth.
Runs as an HTTP service using SSE transport.

Environment variables:
    JIRA_SERVER  — base URL (e.g. http://localhost:8080)
    JIRA_USER    — username or email
    JIRA_TOKEN   — API token or password
    MCP_PORT     — port for the MCP HTTP server (default: 8081)
    MCP_HOST     — host to bind to (default: 0.0.0.0)
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration — fail fast if env vars are missing
# ---------------------------------------------------------------------------

JIRA_SERVER = os.environ.get("JIRA_SERVER")
JIRA_USER = os.environ.get("JIRA_USER")
JIRA_TOKEN = os.environ.get("JIRA_TOKEN")

_missing = [v for v, val in [("JIRA_SERVER", JIRA_SERVER), ("JIRA_USER", JIRA_USER), ("JIRA_TOKEN", JIRA_TOKEN)] if not val]
if _missing:
    print(f"Error: missing required environment variables: {', '.join(_missing)}", file=sys.stderr)
    sys.exit(1)

MCP_PORT = int(os.environ.get("MCP_PORT", "8081"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

JIRA_SERVER = JIRA_SERVER.rstrip("/")
_credentials = base64.b64encode(f"{JIRA_USER}:{JIRA_TOKEN}".encode()).decode()
_AUTH_HEADER = f"Basic {_credentials}"

mcp = FastMCP("atlassian", host=MCP_HOST, port=MCP_PORT)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: dict | None = None) -> dict | str:
    """Make an authenticated HTTP request to the Jira API.

    Returns the parsed JSON response, or an error dict on failure.
    """
    url = f"{JIRA_SERVER}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None

    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": _AUTH_HEADER,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            if not resp_body:
                return {"status": resp.status, "message": "Success"}
            return json.loads(resp_body)
    except urllib.error.HTTPError as exc:
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8")
        except Exception:
            pass
        return {
            "error": True,
            "status": exc.code,
            "message": exc.reason,
            "body": error_body,
        }
    except urllib.error.URLError as exc:
        return {
            "error": True,
            "status": 0,
            "message": f"Connection error: {exc.reason}",
        }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def getJiraIssue(issueIdOrKey: str) -> dict:
    """Get a Jira issue by key or ID.

    Returns the full issue JSON including key, fields (summary, description,
    priority, status, labels, issuetype, comment, etc.).
    """
    return _request("GET", f"/rest/api/2/issue/{issueIdOrKey}")


@mcp.tool()
def searchJiraIssuesUsingJql(
    jql: str,
    maxResults: int = 50,
    fields: Optional[list[str]] = None,
) -> dict:
    """Search for Jira issues using JQL.

    Returns the search response with issues array, total, startAt, and maxResults.
    """
    body: dict = {"jql": jql, "maxResults": maxResults}
    if fields is not None:
        body["fields"] = fields
    return _request("POST", "/rest/api/2/search", body)


@mcp.tool()
def createJiraIssue(
    projectKey: str,
    issueTypeName: str,
    summary: str,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    labels: Optional[list[str]] = None,
    additionalFields: Optional[dict] = None,
) -> dict:
    """Create a new Jira issue.

    Returns the created issue response with id, key, and self URL.
    """
    fields: dict = {
        "project": {"key": projectKey},
        "issuetype": {"name": issueTypeName},
        "summary": summary,
    }
    if description is not None:
        fields["description"] = description
    if priority is not None:
        fields["priority"] = {"name": priority}
    if labels is not None:
        fields["labels"] = labels
    if additionalFields:
        fields.update(additionalFields)

    return _request("POST", "/rest/api/2/issue", {"fields": fields})


@mcp.tool()
def editJiraIssue(issueIdOrKey: str, fields: dict) -> dict:
    """Update fields on an existing Jira issue.

    The fields dict contains field names mapped to new values,
    e.g. {"summary": "new title", "description": "updated"}.
    """
    result = _request("PUT", f"/rest/api/2/issue/{issueIdOrKey}", {"fields": fields})
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"status": 204, "message": f"Issue {issueIdOrKey} updated successfully"}


@mcp.tool()
def addCommentToJiraIssue(issueIdOrKey: str, body: str) -> dict:
    """Add a comment to a Jira issue.

    The body parameter is the comment text (plain text or ADF JSON string).
    """
    return _request("POST", f"/rest/api/2/issue/{issueIdOrKey}/comment", {"body": body})


@mcp.tool()
def getTransitionsForJiraIssue(issueIdOrKey: str) -> dict:
    """Get available workflow transitions for a Jira issue."""
    return _request("GET", f"/rest/api/2/issue/{issueIdOrKey}/transitions")


@mcp.tool()
def transitionJiraIssue(
    issueIdOrKey: str,
    transitionId: str,
    fields: Optional[dict] = None,
) -> dict:
    """Perform a workflow transition on a Jira issue."""
    payload: dict = {"transition": {"id": transitionId}}
    if fields:
        payload["fields"] = fields
    result = _request("POST", f"/rest/api/2/issue/{issueIdOrKey}/transitions", payload)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"status": 204, "message": f"Issue {issueIdOrKey} transitioned successfully"}


# ---------------------------------------------------------------------------
# Multipart upload helper
# ---------------------------------------------------------------------------

def _multipart_request(method: str, path: str, filename: str, file_bytes: bytes, content_type: str = "application/octet-stream") -> dict | str:
    """Make a multipart/form-data request for file upload."""
    boundary = "----JiraMCPBoundary9876543210"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        f"\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    url = f"{JIRA_SERVER}{path}"
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": _AUTH_HEADER,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            if not resp_body:
                return {"status": resp.status, "message": "Success"}
            return json.loads(resp_body)
    except urllib.error.HTTPError as exc:
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8")
        except Exception:
            pass
        return {
            "error": True,
            "status": exc.code,
            "message": exc.reason,
            "body": error_body,
        }
    except urllib.error.URLError as exc:
        return {
            "error": True,
            "status": 0,
            "message": f"Connection error: {exc.reason}",
        }


# ---------------------------------------------------------------------------
# Attachment tools
# ---------------------------------------------------------------------------


@mcp.tool()
def addAttachmentToJiraIssue(issueIdOrKey: str, filename: str, fileContent: str) -> dict:
    """Add a file attachment to a Jira issue.

    The fileContent parameter must be base64-encoded file data.
    Returns the attachment metadata array from the server.
    """
    try:
        file_bytes = base64.b64decode(fileContent)
    except Exception as exc:
        return {"error": True, "message": f"Invalid base64 content: {exc}"}

    import mimetypes
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    return _multipart_request(
        "POST",
        f"/rest/api/2/issue/{issueIdOrKey}/attachments",
        filename,
        file_bytes,
        content_type,
    )


@mcp.tool()
def getJiraIssueAttachments(issueIdOrKey: str) -> dict:
    """Get the list of attachments on a Jira issue.

    Returns the attachment array from the issue's fields.
    """
    result = _request("GET", f"/rest/api/2/issue/{issueIdOrKey}?fields=attachment")
    if isinstance(result, dict) and not result.get("error"):
        return result.get("fields", {}).get("attachment", [])
    return result


@mcp.tool()
def deleteJiraAttachment(attachmentId: str) -> dict:
    """Delete a Jira attachment by its ID.

    Returns success status or error details.
    """
    result = _request("DELETE", f"/rest/api/2/attachment/{attachmentId}")
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"status": 204, "message": f"Attachment {attachmentId} deleted successfully"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Starting Atlassian MCP server on {MCP_HOST}:{MCP_PORT}", file=sys.stderr)
    print(f"Jira backend: {JIRA_SERVER}", file=sys.stderr)
    print(f"SSE endpoint: http://{MCP_HOST}:{MCP_PORT}/sse", file=sys.stderr)
    mcp.run(transport="sse")
