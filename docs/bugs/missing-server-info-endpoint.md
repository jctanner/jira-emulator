# Missing Jira `serverInfo` endpoint

## Summary

The Jira emulator does not implement Jira's `GET /rest/api/2/serverInfo`
endpoint (or its v3 equivalent). Clients that use the standard Jira endpoint
for a connectivity or capability check receive a 404 response.

## Reproduction

With the emulator running, send:

```bash
curl -u admin:admin http://localhost:8080/rest/api/2/serverInfo
```

The request returns `404 Not Found`. The equivalent v3 request is also
unavailable:

```bash
curl -u admin:admin http://localhost:8080/rest/api/3/serverInfo
```

## Expected behavior

Both API versions should return a Jira-compatible server information object,
including the base URL, display name, version, version numbers, deployment
type, and build information. The response should follow the emulator's normal
authentication behavior and be covered by the REST v2 and REST v3 test suites.

## Impact

Jira-compatible clients and service status checks commonly use `serverInfo` to
confirm that a Jira endpoint is reachable before issuing searches or other
operations. They currently report the emulator as unavailable even though the
REST API is healthy. The current readiness probe works around this by using
`GET /rest/api/2/priority` instead.

## Acceptance criteria

- Implement `GET /rest/api/2/serverInfo`.
- Make `GET /rest/api/3/serverInfo` follow the emulator's v3 compatibility
  behavior.
- Return a stable Jira-compatible response shape with emulator-appropriate
  values.
- Add authenticated and unauthenticated behavior tests for both API versions,
  consistent with the configured auth mode.
- Document the endpoint in the REST API reference and endpoint catalog.
