# Jira ServerInfo Response Schema

**Endpoint:** `https://example.atlassian.net/rest/api/2/serverInfo`

URLs and the server title below are sanitized examples. They preserve the
observed Atlassian Cloud response shape without identifying the source tenant.

**Date:** 2026-09-16

## Response

```json
{
  "baseUrl": "https://example.atlassian.net",
  "displayUrl": "https://example.atlassian.net",
  "displayUrlServicedeskHelpCenter": "https://example.atlassian.net",
  "displayUrlCSMHelpSeeker": "https://example.atlassian.net",
  "displayUrlConfluence": "https://example.atlassian.net",
  "version": "1001.0.0-SNAPSHOT",
  "versionNumbers": [1001, 0, 0],
  "deploymentType": "Cloud",
  "buildNumber": 100294,
  "buildDate": "2026-09-16T10:53:30.000+0000",
  "scmInfo": "96a650f8ce7261578cc2cd25dbe6ec0ad6dcb258",
  "serverTitle": "Example Issue Tracker",
  "defaultLocale": {
    "locale": "en_US"
  },
  "serverTimeZone": "Etc/UTC"
}
```

## Field Descriptions

| Field | Value | Description |
|-------|-------|-------------|
| `baseUrl` | `https://example.atlassian.net` | Base URL for the Jira instance |
| `displayUrl` | `https://example.atlassian.net` | URL displayed to users |
| `displayUrlServicedeskHelpCenter` | `https://example.atlassian.net` | Service Desk Help Center URL |
| `displayUrlCSMHelpSeeker` | `https://example.atlassian.net` | CSM Help Seeker URL |
| `displayUrlConfluence` | `https://example.atlassian.net` | Confluence display URL |
| `version` | `1001.0.0-SNAPSHOT` | Jira version string |
| `versionNumbers` | `[1001, 0, 0]` | Major, minor, patch version numbers |
| `deploymentType` | `Cloud` | Deployment type (Cloud instance) |
| `buildNumber` | `100294` | Build number |
| `buildDate` | `2026-09-16T10:53:30.000+0000` | Build date and time |
| `scmInfo` | `96a650f8ce7261578cc2cd25dbe6ec0ad6dcb258` | SCM commit hash |
| `serverTitle` | `Example Issue Tracker` | Server display title |
| `defaultLocale.locale` | `en_US` | Default locale |
| `serverTimeZone` | `Etc/UTC` | Server timezone |

## Notes

- The observed endpoint redirected from a legacy Jira hostname to Atlassian Cloud.
- This is an Atlassian Cloud instance, not self-hosted
- Version appears to be snapshot/development build
