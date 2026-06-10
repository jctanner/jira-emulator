#!/usr/bin/env python3
"""Export issues from a Jira-compatible server with full pagination.

Reads JIRA_USER and JIRA_API_TOKEN from .env, paginates through
POST /rest/api/2/search/jql, and writes raw API responses to a JSON file.

Usage:
    uv run python scripts/issue-export.py --project RHOAIENG
    uv run python scripts/issue-export.py --project RHOAIENG --output exports/rhoaieng-issues.json
    uv run python scripts/issue-export.py --project RHOAIENG --server http://localhost:8080
    uv run python scripts/issue-export.py --project RHOAIENG --jql "status = Open"
    uv run python scripts/issue-export.py --project RHOAIENG --max-results 100
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

DEFAULT_SERVER = "https://redhat.atlassian.net"


def load_dotenv(path: str = ".env") -> dict[str, str]:
    """Parse a .env file into a dict. Handles quotes and comments."""
    env: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return env
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


class JiraIssueExporter:
    def __init__(self, server: str, user: str, token: str, project_key: str):
        self.server = server.rstrip("/")
        self.project_key = project_key
        creds = base64.b64encode(f"{user}:{token}".encode()).decode()
        self.client = httpx.Client(
            base_url=self.server,
            headers={
                "Authorization": f"Basic {creds}",
                "Accept": "application/json",
            },
            timeout=60.0,
        )

    def _post(self, path: str, **kwargs) -> dict:
        resp = self.client.post(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, **kwargs) -> dict | list:
        resp = self.client.get(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _get_issue(self, key: str) -> dict:
        """Fetch a single issue with all fields, comments, attachments, and links."""
        return self._get(f"/rest/api/2/issue/{key}")

    def _search_keys(self, jql: str, max_results: int) -> list[str]:
        """Paginate through search to collect all issue keys using cursor pagination."""
        keys: list[str] = []
        next_page_token: str | None = None

        while True:
            body: dict = {
                "jql": jql,
                "maxResults": max_results,
                "fields": ["key"],
            }
            if next_page_token is not None:
                body["nextPageToken"] = next_page_token

            data = self._post("/rest/api/2/search/jql", json=body)

            total = data.get("total", "?")

            issues = data.get("issues", [])
            if not issues:
                break

            keys.extend(i["key"] for i in issues)
            print(f"  Discovered {len(keys)}/{total} keys...", file=sys.stderr)

            if data.get("isLast", True):
                break

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        return keys

    def export(self, jql_extra: str | None = None, max_results: int = 50) -> dict:
        jql = f"project = {self.project_key}"
        if jql_extra:
            jql = f"{jql} AND {jql_extra}"

        print(f"Exporting issues: {jql}", file=sys.stderr)
        print(f"  Server: {self.server}", file=sys.stderr)
        print(f"  Page size: {max_results}", file=sys.stderr)

        resp = self.client.get("/rest/api/2/myself")
        if resp.status_code == 200:
            me = resp.json()
            print(f"  Authenticated as: {me.get('displayName', '?')} ({me.get('emailAddress', '?')})", file=sys.stderr)
        else:
            print(f"  Auth check failed: HTTP {resp.status_code}", file=sys.stderr)
            print(f"  {resp.text[:300]}", file=sys.stderr)
            sys.exit(1)

        keys = self._search_keys(jql, max_results)

        print(f"  Fetching full issue details ({len(keys)} issues)...", file=sys.stderr)
        all_issues: list[dict] = []
        for i, key in enumerate(keys, 1):
            issue = self._get_issue(key)
            all_issues.append(issue)
            if i % 25 == 0 or i == len(keys):
                print(f"  Fetched {i}/{len(keys)} issues...", file=sys.stderr)

        return {
            "metadata": {
                "exported_at": datetime.now(UTC).isoformat(),
                "source": self.server,
                "project": self.project_key,
                "jql": jql,
                "total": len(all_issues),
            },
            "issues": all_issues,
        }


def main():
    parser = argparse.ArgumentParser(description="Export issues from a Jira-compatible server")
    parser.add_argument("--project", required=True, help="Jira project key (e.g. RHOAIENG)")
    parser.add_argument("--output", help="Output JSON file (default: exports/{PROJECT}-issues.json)")
    parser.add_argument("--server", help=f"Jira server URL (default: {DEFAULT_SERVER})")
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Results per page (default: 50, max 1000)",
    )
    parser.add_argument(
        "--jql",
        help='Additional JQL filter appended to "project = KEY" (e.g. "status = Open")',
    )
    args = parser.parse_args()

    dotenv = load_dotenv()

    server = args.server or os.environ.get("JIRA_SERVER") or dotenv.get("JIRA_SERVER") or DEFAULT_SERVER
    user = os.environ.get("JIRA_USER") or dotenv.get("JIRA_USER")
    token = os.environ.get("JIRA_API_TOKEN") or dotenv.get("JIRA_API_TOKEN")

    if not user:
        print("Error: JIRA_USER not set in .env or environment", file=sys.stderr)
        sys.exit(1)
    if not token:
        print("Error: JIRA_API_TOKEN not set in .env or environment", file=sys.stderr)
        sys.exit(1)

    max_results = min(max(1, args.max_results), 1000)
    output_path = Path(args.output) if args.output else Path("exports") / f"{args.project}-issues.json"

    exporter = JiraIssueExporter(server, user, token, args.project)

    try:
        result = exporter.export(jql_extra=args.jql, max_results=max_results)
    except httpx.HTTPStatusError as exc:
        print(
            f"Error: HTTP {exc.response.status_code} from {exc.request.url}",
            file=sys.stderr,
        )
        body = exc.response.text[:500]
        if body:
            print(f"  {body}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n")

    total_comments = sum(len(i.get("fields", {}).get("comment", {}).get("comments", [])) for i in result["issues"])
    total_attachments = sum(len(i.get("fields", {}).get("attachment", [])) for i in result["issues"])
    total_links = sum(len(i.get("fields", {}).get("issuelinks", [])) for i in result["issues"])

    print(f"\nExport complete: {output_path}", file=sys.stderr)
    print(f"  Project:     {result['metadata']['project']}", file=sys.stderr)
    print(f"  JQL:         {result['metadata']['jql']}", file=sys.stderr)
    print(f"  Issues:      {result['metadata']['total']}", file=sys.stderr)
    print(f"  Comments:    {total_comments}", file=sys.stderr)
    print(f"  Attachments: {total_attachments}", file=sys.stderr)
    print(f"  Links:       {total_links}", file=sys.stderr)


if __name__ == "__main__":
    main()
