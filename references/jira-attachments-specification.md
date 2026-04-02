# Jira Attachments — Complete Specification

Collected from Atlassian developer documentation and community resources, April 2026.

## Sources

- https://developer.atlassian.com/cloud/jira/platform/rest/v2/api-group-issue-attachments/
- https://developer.atlassian.com/cloud/jira/platform/rest/v2/intro/
- https://support.atlassian.com/jira/kb/how-to-add-an-attachment-to-a-jira-issue-using-rest-api/
- https://docs.atlassian.com/software/jira/docs/api/REST/1000.919.0/
- https://docs.atlassian.com/software/jira/docs/api/7.6.1/com/atlassian/jira/rest/v2/issue/IssueAttachmentsResource.html
- https://community.developer.atlassian.com/t/deprecation-of-obsolete-jira-cloud-download-attachment-and-thumbnail-urls/63171

---

## 1. REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rest/api/2/issue/{issueIdOrKey}/attachments` | Upload attachment(s) to an issue |
| GET | `/rest/api/2/attachment/{id}` | Get attachment metadata |
| DELETE | `/rest/api/2/attachment/{id}` | Delete an attachment |
| GET | `/rest/api/2/attachment/content/{id}` | Download attachment file bytes |
| GET | `/rest/api/2/attachment/thumbnail/{id}` | Download attachment thumbnail |
| GET | `/rest/api/2/attachment/meta` | Get attachment settings (enabled, max size) |
| GET | `/rest/api/2/attachment/{id}/expand/human` | Expand archive contents (human-readable) |
| GET | `/rest/api/2/attachment/{id}/expand/raw` | Expand archive contents (machine-readable) |

---

## 2. Upload: POST /rest/api/2/issue/{issueIdOrKey}/attachments

### Request

- **Content-Type**: `multipart/form-data`
- **File field name**: `file` (mandatory name — the multipart parameter **must** be named `file`)
- **Multiple files**: Supported via multiple `file` fields in the same request

### Required Headers

```
X-Atlassian-Token: no-check
Content-Type: multipart/form-data
Accept: application/json
```

The `X-Atlassian-Token: no-check` header is **mandatory**. Without it, CSRF protection blocks the request. Both `no-check` and `nocheck` are accepted; `no-check` is canonical.

### curl Examples

Single file:
```bash
curl -u admin:admin -X POST \
  -H "X-Atlassian-Token: no-check" \
  -H "Accept: application/json" \
  -F "file=@myfile.txt" \
  http://localhost:8080/rest/api/2/issue/TEST-123/attachments
```

Multiple files:
```bash
curl -u admin:admin -X POST \
  -H "X-Atlassian-Token: no-check" \
  -F "file=@report.pdf" \
  -F "file=@screenshot.png" \
  http://localhost:8080/rest/api/2/issue/TEST-123/attachments
```

### Python Example

```python
import requests

url = "http://localhost:8080/rest/api/2/issue/TEST-123/attachments"
headers = {
    "X-Atlassian-Token": "no-check",
    "Accept": "application/json",
}
# Do NOT set Content-Type manually — requests sets the multipart boundary.
files = [
    ("file", ("myfile.txt", open("myfile.txt", "rb"), "text/plain"))
]
response = requests.post(url, headers=headers, files=files, auth=("admin", "admin"))
```

### Response

**Status**: `200 OK`

**Body**: JSON **array** of attachment objects (one per uploaded file):

```json
[
  {
    "self": "http://localhost:8080/rest/api/2/attachment/10001",
    "id": "10001",
    "filename": "picture.jpg",
    "author": {
      "self": "http://localhost:8080/rest/api/2/user?username=admin",
      "name": "admin",
      "key": "admin",
      "emailAddress": "",
      "displayName": "admin",
      "active": true,
      "timeZone": "UTC"
    },
    "created": "2026-04-02T14:47:28.592+0000",
    "size": 23123,
    "mimeType": "image/jpeg",
    "content": "http://localhost:8080/rest/api/2/attachment/content/10001",
    "thumbnail": "http://localhost:8080/rest/api/2/attachment/thumbnail/10001"
  }
]
```

### Error Responses

| Status | Meaning |
|--------|---------|
| `403` | Attachments disabled or user lacks permission |
| `404` | Issue not found |
| `413` | Attachment exceeds the configured upload limit |

---

## 3. Attachment Object Schema

Every attachment endpoint returns objects with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `self` | string (URI) | REST API URL of this attachment resource |
| `id` | string | Unique numeric ID (returned as string in JSON) |
| `filename` | string | Original filename |
| `author` | object (User) | The user who uploaded the attachment |
| `created` | string (datetime) | ISO 8601 timestamp, e.g. `"2026-04-02T14:47:28.592+0000"` |
| `size` | integer | File size in bytes |
| `mimeType` | string | MIME type, e.g. `"image/jpeg"`, `"text/plain"`, `"application/pdf"` |
| `content` | string (URI) | URL to download the actual file bytes |
| `thumbnail` | string (URI) or null | URL for thumbnail (image attachments only; absent/null for non-images) |

### Full Example (Jira Server Style)

```json
{
  "self": "http://localhost:8080/rest/api/2/attachment/10000",
  "id": "10000",
  "filename": "picture.jpg",
  "author": {
    "self": "http://localhost:8080/rest/api/2/user?username=fred",
    "name": "fred",
    "key": "fred",
    "emailAddress": "fred@example.com",
    "displayName": "Fred F. User",
    "active": true,
    "timeZone": "UTC"
  },
  "created": "2026-04-02T14:47:28.592+0000",
  "size": 23123,
  "mimeType": "image/jpeg",
  "content": "http://localhost:8080/rest/api/2/attachment/content/10000",
  "thumbnail": "http://localhost:8080/rest/api/2/attachment/thumbnail/10000"
}
```

---

## 4. Get Attachment Metadata: GET /rest/api/2/attachment/{id}

Returns a **single** attachment JSON object (not an array).

**Response** (`200 OK`): Same schema as section 3.

**Errors**: `403` (no permission), `404` (not found or attachments disabled).

---

## 5. Delete Attachment: DELETE /rest/api/2/attachment/{id}

**Response**: `204 No Content` — empty body on success.

**Errors**: `403` (no permission), `404` (not found).

---

## 6. Download Content: GET /rest/api/2/attachment/content/{id}

Returns the **raw file bytes** with appropriate `Content-Type` and `Content-Disposition` headers.

Supports HTTP `Range` header for partial downloads.

### Legacy vs. Modern URLs

| URL Format | Status |
|------------|--------|
| `/secure/attachment/{id}/{filename}` | Deprecated/removed on Cloud |
| `/rest/api/2/attachment/content/{id}` | Current (Cloud and Server) |

---

## 7. Download Thumbnail: GET /rest/api/2/attachment/thumbnail/{id}

Returns a thumbnail image for image-type attachments.

- Jira auto-generates thumbnails for JPEG, PNG, GIF, BMP, etc.
- Default thumbnail size: **200×200 pixels**
- Non-image files have no thumbnail (the `thumbnail` field is absent/null)

---

## 8. Attachment Settings: GET /rest/api/2/attachment/meta

Returns global attachment configuration.

**Response** (`200 OK`):

```json
{
  "enabled": true,
  "uploadLimit": 10485760
}
```

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Whether attachments are enabled |
| `uploadLimit` | integer | Maximum upload size in bytes (default 10 MB = 10485760) |

---

## 9. Attachments in Issue GET Response

Attachments appear as `fields.attachment` — always an array, even when empty.

```json
{
  "id": "10001",
  "key": "PROJ-123",
  "fields": {
    "attachment": [
      {
        "self": "http://localhost:8080/rest/api/2/attachment/10000",
        "id": "10000",
        "filename": "picture.jpg",
        "author": { ... },
        "created": "2026-04-02T14:47:28.592+0000",
        "size": 23123,
        "mimeType": "image/jpeg",
        "content": "http://localhost:8080/rest/api/2/attachment/content/10000",
        "thumbnail": "http://localhost:8080/rest/api/2/attachment/thumbnail/10000"
      }
    ]
  }
}
```

Can be requested selectively with `?fields=attachment`.

---

## 10. MCP (Model Context Protocol) and Attachments

### Current MCP Spec Status

MCP tool inputs are JSON Schema-based — there is **no native binary/file parameter type**. Tool outputs support `ImageContent`, `AudioContent`, and `EmbeddedResource` (with base64 `blob` field) for binary data.

### How Existing Jira MCP Servers Handle Attachments

| Server | Upload Approach | Download Approach |
|--------|----------------|-------------------|
| [cosmix/jira-mcp](https://github.com/cosmix/jira-mcp) | `add_attachment` tool: accepts `issueKey`, `fileContent` (base64 string), `filename` | N/A |
| [vish288/mcp-atlassian-extended](https://github.com/vish288/mcp-atlassian-extended) | `jira_upload_attachment`: accepts file path (local servers only) | `jira_download_attachment`: saves to local path |
| [pdogra1299/jira-mcp-server](https://github.com/pdogra1299/jira-mcp-server) | Full lifecycle: list, upload, delete, retrieve content | Returns text files as text; images inline via vision |
| [atlassian/atlassian-mcp-server](https://github.com/atlassian/atlassian-mcp-server) (Official) | **Not supported** — [Issue #63](https://github.com/atlassian/atlassian-mcp-server/issues/63) open | Not supported |

### Recommended MCP Tool Design for Emulator

#### Upload Tool: `addAttachmentToJiraIssue`

```python
@mcp.tool()
def addAttachmentToJiraIssue(
    issueIdOrKey: str,     # e.g. "TEST-123"
    filename: str,         # e.g. "report.pdf"
    fileContent: str,      # base64-encoded file bytes
) -> dict:
    """Upload an attachment to a Jira issue."""
    # Decode base64, POST as multipart/form-data to
    # /rest/api/2/issue/{issueIdOrKey}/attachments
    # with X-Atlassian-Token: no-check header
```

#### List/Get Tool: `getJiraIssueAttachments`

```python
@mcp.tool()
def getJiraIssueAttachments(
    issueIdOrKey: str,     # e.g. "TEST-123"
) -> dict:
    """List all attachments on a Jira issue."""
    # GET /rest/api/2/issue/{issueIdOrKey}?fields=attachment
    # Return the fields.attachment array
```

#### Delete Tool: `deleteJiraAttachment`

```python
@mcp.tool()
def deleteJiraAttachment(
    attachmentId: str,     # e.g. "10001"
) -> dict:
    """Delete a Jira attachment by ID."""
    # DELETE /rest/api/2/attachment/{attachmentId}
```

### Future Spec Work

- [SEP-1306](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1306) proposes binary file upload elicitation (exploratory, not ratified)
- [Discussion #1197](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1197) discusses passing files from client to server

---

## 11. Emulator Implementation Notes

### What Currently Exists

The emulator returns a hardcoded empty attachment array in `format_issue_response()` at `issue_service.py:1023`:

```python
"attachment": [],
```

### What Needs to Be Built

1. **Attachment model**: `id`, `issue_id` (FK), `author_id` (FK), `filename`, `size` (int bytes), `mime_type`, `created_at`, plus file storage (disk path or BLOB)
2. **File storage**: Store uploaded files on disk under a configurable directory (e.g. `data/attachments/{id}_{filename}`)
3. **Upload endpoint**: `POST /rest/api/2/issue/{issueIdOrKey}/attachments` — accept multipart/form-data, check `X-Atlassian-Token` header, return array of attachment objects
4. **Metadata endpoint**: `GET /rest/api/2/attachment/{id}` — return single attachment object
5. **Delete endpoint**: `DELETE /rest/api/2/attachment/{id}` — return 204
6. **Content endpoint**: `GET /rest/api/2/attachment/content/{id}` — return raw file bytes with correct Content-Type
7. **Thumbnail endpoint**: `GET /rest/api/2/attachment/thumbnail/{id}` — return scaled image (for image attachments only; 404 for non-images)
8. **Meta endpoint**: `GET /rest/api/2/attachment/meta` — return `{"enabled": true, "uploadLimit": 10485760}`
9. **Issue response**: Populate `fields.attachment` from the attachment model
10. **Web UI**: Attachment list on issue detail page + file upload form
11. **MCP tools**: `addAttachmentToJiraIssue` (base64 upload), `getJiraIssueAttachments` (list), `deleteJiraAttachment` (delete)
12. **History tracking**: Record attachment add/delete in issue history
