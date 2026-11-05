# No way to read the request bodies a client sent

## Status: Fixed

## Summary

Test harnesses need to assert exactly what a client wrote. Examples: that a
strategy run never PUT an issue's `description` or `summary`, or that an
Initiative run touched no Feature. The emulator logged only the method,
path, status and duration.

## Fix

- `request_audit.py`: a pure ASGI middleware, installed outermost so it sees
  the path the client sent (before the v3 rewrite). It records every
  non-GET request under `/rest/`: method, path, query, status, Basic-auth
  user, content type, and the body up to `REQUEST_AUDIT_MAX_BODY_BYTES`
  (default 128 KiB). Entries go in a ring of `REQUEST_AUDIT_MAX_ENTRIES`
  (default 2000; 0 disables it).
- `GET /api/admin/requests?since=<seq>&limit=` reads the ring. `DELETE`
  clears it, and sequence numbers keep increasing across clears. Admin
  requests are not recorded.
- The audit is in-memory only. Reset and restore leave it unchanged, and a
  restart empties it.
- Tests: `tests/test_request_audit.py`. These cover v2 and v3 paths and
  bodies, exclusion of admin and read requests, `since` and clearing, the
  body cap, and multipart attachment uploads. MCP tools reach the emulator
  through REST, so their writes are recorded too.
