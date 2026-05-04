#!/usr/bin/env python3
"""Export project configuration from Jira Cloud for jira-emulator import.

Reads JIRA_USER and JIRA_API_TOKEN from .env, hits the Jira REST API v2,
and writes a v1.0 configuration JSON file suitable for import into the
jira-emulator.

Usage:
    uv run python scripts/project-export.py --project RHOAIENG
    uv run python scripts/project-export.py --project RHOAIENG --output exports/rhoaieng.json
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


class JiraProjectExporter:
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
            timeout=30.0,
        )

    def _get(self, path: str, **kwargs) -> dict | list:
        resp = self.client.get(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def export(self) -> dict:
        print(f"Exporting project {self.project_key} from {self.server}", file=sys.stderr)

        project_data = self._export_project()
        project_statuses = self._export_project_statuses()
        issue_types = self._export_issue_types(project_data)
        statuses = self._export_statuses()
        priorities = self._export_priorities()
        resolutions = self._export_resolutions()
        link_types = self._export_link_types()
        fields_raw = self._export_fields()
        createmeta = self._export_createmeta()
        custom_fields = self._build_custom_fields(fields_raw, createmeta)
        workflows, workflow_mappings = self._build_workflows(project_statuses)

        project_issue_type_names = [it["name"] for it in issue_types]

        return {
            "version": "1.0",
            "metadata": {
                "exported_at": datetime.now(UTC).isoformat(),
                "source": self.server,
                "project": self.project_key,
            },
            "project": {
                "key": project_data["key"],
                "name": project_data["name"],
                "description": project_data.get("description", ""),
                "issue_types": project_issue_type_names,
                "workflows": workflow_mappings,
            },
            "issue_types": issue_types,
            "statuses": statuses,
            "priorities": priorities,
            "resolutions": resolutions,
            "link_types": link_types,
            "custom_fields": custom_fields,
            "workflows": workflows,
        }

    def _export_project(self) -> dict:
        print(f"  Fetching project {self.project_key}...", file=sys.stderr)
        return self._get(f"/rest/api/2/project/{self.project_key}")

    def _export_project_statuses(self) -> list[dict]:
        """GET /rest/api/2/project/{key}/statuses — issue types with their workflow statuses."""
        print("  Fetching project statuses...", file=sys.stderr)
        raw = self._get(f"/rest/api/2/project/{self.project_key}/statuses")
        print(f"  Found statuses for {len(raw)} issue types", file=sys.stderr)
        return raw

    def _export_issue_types(self, project_data: dict) -> list[dict]:
        raw_types = project_data.get("issueTypes", [])
        print(f"  Found {len(raw_types)} issue types", file=sys.stderr)
        return [
            {
                "name": it["name"],
                "subtask": it.get("subtask", False),
                "description": it.get("description", ""),
            }
            for it in raw_types
        ]

    def _export_statuses(self) -> list[dict]:
        print("  Fetching statuses...", file=sys.stderr)
        raw = self._get("/rest/api/2/status")
        print(f"  Found {len(raw)} statuses", file=sys.stderr)
        return [
            {
                "status_id": s["id"],
                "name": s["name"],
                "description": s.get("description", ""),
                "status_category": s.get("statusCategory", {}).get("key", "indeterminate"),
                "icon_url": s.get("iconUrl", ""),
            }
            for s in raw
        ]

    def _export_priorities(self) -> list[dict]:
        print("  Fetching priorities...", file=sys.stderr)
        raw = self._get("/rest/api/2/priority")
        print(f"  Found {len(raw)} priorities", file=sys.stderr)
        return [{"name": p["name"], "sort_order": idx + 1} for idx, p in enumerate(raw)]

    def _export_resolutions(self) -> list[dict]:
        print("  Fetching resolutions...", file=sys.stderr)
        raw = self._get("/rest/api/2/resolution")
        print(f"  Found {len(raw)} resolutions", file=sys.stderr)
        return [{"name": r["name"]} for r in raw]

    def _export_link_types(self) -> list[dict]:
        print("  Fetching issue link types...", file=sys.stderr)
        raw = self._get("/rest/api/2/issueLinkType")
        types = raw.get("issueLinkTypes", [])
        print(f"  Found {len(types)} link types", file=sys.stderr)
        return [
            {
                "name": lt["name"],
                "inward_description": lt.get("inward", ""),
                "outward_description": lt.get("outward", ""),
            }
            for lt in types
        ]

    def _export_fields(self) -> list[dict]:
        print("  Fetching fields...", file=sys.stderr)
        raw = self._get("/rest/api/2/field")
        custom = [f for f in raw if f.get("custom")]
        print(f"  Found {len(raw)} fields ({len(custom)} custom)", file=sys.stderr)
        return raw

    def _export_createmeta(self) -> dict:
        print("  Fetching create metadata...", file=sys.stderr)
        try:
            return self._get(
                "/rest/api/2/issue/createmeta",
                params={
                    "projectKeys": self.project_key,
                    "expand": "projects.issuetypes.fields",
                },
            )
        except httpx.HTTPStatusError as exc:
            print(
                f"  Warning: createmeta returned {exc.response.status_code}, field metadata will be incomplete",
                file=sys.stderr,
            )
            return {}

    def _build_custom_fields(self, fields_raw: list[dict], createmeta: dict) -> list[dict]:
        field_metadata: dict[str, dict] = {}
        for project in createmeta.get("projects", []):
            for issuetype in project.get("issuetypes", []):
                it_name = issuetype["name"]
                for field_id, field_meta in issuetype.get("fields", {}).items():
                    if not field_id.startswith("customfield_"):
                        continue
                    if field_id not in field_metadata:
                        field_metadata[field_id] = {
                            "required_for": [],
                            "allowed_values": [],
                            "available_for": [],
                        }
                    meta = field_metadata[field_id]
                    meta["available_for"].append(it_name)
                    if field_meta.get("required"):
                        meta["required_for"].append(it_name)
                    if not meta["allowed_values"] and "allowedValues" in field_meta:
                        meta["allowed_values"] = [
                            v.get("value", v.get("name", str(v))) for v in field_meta["allowedValues"]
                        ]

        custom_fields = []
        for f in fields_raw:
            if not f.get("custom"):
                continue
            fid = f["id"]
            schema = f.get("schema", {})
            meta = field_metadata.get(fid, {})

            if not meta.get("available_for") and field_metadata:
                continue

            custom_fields.append(
                {
                    "field_id": fid,
                    "name": f["name"],
                    "field_type": schema.get("type", "string"),
                    "description": "",
                    "schema_type": schema.get("type", "string"),
                    "schema_custom": schema.get("custom", ""),
                    "required_for": meta.get("required_for", []),
                    "allowed_values": meta.get("allowed_values", []),
                    "available_for": meta.get("available_for", []),
                }
            )

        print(f"  Mapped {len(custom_fields)} custom fields for project", file=sys.stderr)
        return custom_fields

    def _build_workflows(self, project_statuses: list[dict]) -> tuple[list[dict], list[dict]]:
        workflows = []
        mappings = []
        seen_status_sets: dict[tuple, str] = {}
        wf_counter = 0

        for it in project_statuses:
            statuses = it.get("statuses", [])
            if not statuses:
                continue

            status_key = tuple(s["id"] for s in statuses)

            if status_key in seen_status_sets:
                wf_id = seen_status_sets[status_key]
            else:
                wf_counter += 1
                wf_id = str(wf_counter)
                seen_status_sets[status_key] = wf_id
                workflows.append(
                    {
                        "workflow_id": wf_id,
                        "name": f"{it['name']} Workflow",
                        "statuses": [{"status_id": s["id"], "sequence": idx + 1} for idx, s in enumerate(statuses)],
                    }
                )

            mappings.append(
                {
                    "issue_type": it["name"],
                    "workflow_id": wf_id,
                }
            )

        print(f"  Derived {len(workflows)} unique workflows from {len(mappings)} issue type mappings", file=sys.stderr)
        return workflows, mappings


def main():
    parser = argparse.ArgumentParser(description="Export Jira project configuration for jira-emulator import")
    parser.add_argument("--project", required=True, help="Jira project key (e.g. RHOAIENG)")
    parser.add_argument("--output", help="Output JSON file (default: exports/{PROJECT}.json)")
    parser.add_argument("--server", help=f"Jira server URL (default: {DEFAULT_SERVER})")
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

    output_path = Path(args.output) if args.output else Path("exports") / f"{args.project}.json"

    exporter = JiraProjectExporter(server, user, token, args.project)

    try:
        config = exporter.export()
    except httpx.HTTPStatusError as exc:
        print(f"Error: HTTP {exc.response.status_code} from {exc.request.url}", file=sys.stderr)
        body = exc.response.text[:500]
        if body:
            print(f"  {body}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(config, indent=2) + "\n")

    print(f"\nExport complete: {output_path}", file=sys.stderr)
    print(f"  Project:       {config['project']['key']} ({config['project']['name']})", file=sys.stderr)
    print(f"  Issue types:   {len(config['issue_types'])}", file=sys.stderr)
    print(f"  Statuses:      {len(config['statuses'])}", file=sys.stderr)
    print(f"  Priorities:    {len(config['priorities'])}", file=sys.stderr)
    print(f"  Resolutions:   {len(config['resolutions'])}", file=sys.stderr)
    print(f"  Link types:    {len(config['link_types'])}", file=sys.stderr)
    print(f"  Custom fields: {len(config['custom_fields'])}", file=sys.stderr)
    print(f"  Workflows:     {len(config['workflows'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
