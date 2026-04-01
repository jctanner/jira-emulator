# Jira API Deprecation Notes (2025-2026)

## Sources

- https://docs.adaptavist.com/sr4jc/latest/release-notes/breaking-changes/atlassian-rest-api-search-endpoints-deprecation
- https://community.atlassian.com/forums/Jira-questions/Clarification-on-Deprecation-of-rest-api-3-search-and-rest-api-2/qaq-p/2931794
- https://community.atlassian.com/forums/Jira-questions/Sunset-schedule-for-Issue-API-CHANGE-2046/qaq-p/3105876

## Search API Deprecation

Atlassian deprecated the Jira Cloud search APIs on October 31, 2024:

| Old Endpoint | New Endpoint | Sunset Date |
|--------------|-------------|-------------|
| `GET /rest/api/2/search` | `POST /rest/api/2/search/jql` | August 1, 2025 |
| `POST /rest/api/2/search` | `POST /rest/api/2/search/jql` | August 1, 2025 |
| `GET /rest/api/3/search` | `POST /rest/api/3/search/jql` | August 1, 2025 |
| `POST /rest/api/3/search` | `POST /rest/api/3/search/jql` | August 1, 2025 |

### New Search API Changes

- Uses `POST /rest/api/2/search/jql` with JSON body
- Response uses `nextPageToken` instead of `startAt` for pagination
- Progressive rollout by region

### Projects API

| Old Endpoint | New Endpoint |
|--------------|-------------|
| `GET /rest/api/2/project` (get all) | `GET /rest/api/2/project/search` (paginated) |

### Issue API Unchanged

- `GET /rest/api/2/issue/{key}` - still available, not deprecated
- `POST /rest/api/2/issue` - still available
- `PUT /rest/api/2/issue/{key}` - still available

## Relevance to Emulator

Since our emulator targets the `jira-python` library (which uses v2 API internally) and
our own client code, we should implement BOTH the old and new search endpoints:

1. **`POST /rest/api/2/search`** - for compatibility with existing `jira-python` library
2. **`GET /rest/api/2/search`** - for simple query-string-based searches
3. Optionally: **`POST /rest/api/2/search/jql`** - for forward compatibility

The emulator does NOT need to worry about sunset dates since it's our own server.
