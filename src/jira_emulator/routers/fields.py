"""Field listing endpoint: /rest/api/2/field."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jira_emulator.auth.middleware import get_current_user
from jira_emulator.config import get_settings
from jira_emulator.database import get_db
from jira_emulator.models.custom_field import CustomField
from jira_emulator.models.user import User

router = APIRouter(prefix="/rest/api/2")

# Hardcoded system fields matching Jira's standard field definitions
SYSTEM_FIELDS = [
    {
        "id": "summary",
        "name": "Summary",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["summary"],
        "schema": {"type": "string", "system": "summary"},
    },
    {
        "id": "status",
        "name": "Status",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["status"],
        "schema": {"type": "status", "system": "status"},
    },
    {
        "id": "priority",
        "name": "Priority",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["priority"],
        "schema": {"type": "priority", "system": "priority"},
    },
    {
        "id": "assignee",
        "name": "Assignee",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["assignee"],
        "schema": {"type": "user", "system": "assignee"},
    },
    {
        "id": "reporter",
        "name": "Reporter",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["reporter"],
        "schema": {"type": "user", "system": "reporter"},
    },
    {
        "id": "issuetype",
        "name": "Issue Type",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["issuetype", "type"],
        "schema": {"type": "issuetype", "system": "issuetype"},
    },
    {
        "id": "project",
        "name": "Project",
        "custom": False,
        "orderable": False,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["project"],
        "schema": {"type": "project", "system": "project"},
    },
    {
        "id": "description",
        "name": "Description",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["description"],
        "schema": {"type": "string", "system": "description"},
    },
    {
        "id": "labels",
        "name": "Labels",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["labels"],
        "schema": {"type": "array", "items": "string", "system": "labels"},
    },
    {
        "id": "components",
        "name": "Component/s",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["component"],
        "schema": {
            "type": "array",
            "items": "component",
            "system": "components",
        },
    },
    {
        "id": "fixVersions",
        "name": "Fix Version/s",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["fixVersion"],
        "schema": {
            "type": "array",
            "items": "version",
            "system": "fixVersions",
        },
    },
    {
        "id": "versions",
        "name": "Affects Version/s",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["affectedVersion"],
        "schema": {
            "type": "array",
            "items": "version",
            "system": "versions",
        },
    },
    {
        "id": "created",
        "name": "Created",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["created", "createdDate"],
        "schema": {"type": "datetime", "system": "created"},
    },
    {
        "id": "updated",
        "name": "Updated",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["updated", "updatedDate"],
        "schema": {"type": "datetime", "system": "updated"},
    },
    {
        "id": "resolution",
        "name": "Resolution",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["resolution"],
        "schema": {"type": "resolution", "system": "resolution"},
    },
    {
        "id": "duedate",
        "name": "Due Date",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": True,
        "clauseNames": ["due", "duedate"],
        "schema": {"type": "date", "system": "duedate"},
    },
    {
        "id": "comment",
        "name": "Comment",
        "custom": False,
        "orderable": True,
        "navigable": False,
        "searchable": True,
        "clauseNames": ["comment"],
        "schema": {"type": "comments-page", "system": "comment"},
    },
    {
        "id": "issuelinks",
        "name": "Linked Issues",
        "custom": False,
        "orderable": True,
        "navigable": True,
        "searchable": False,
        "clauseNames": [],
        "schema": {
            "type": "array",
            "items": "issuelinks",
            "system": "issuelinks",
        },
    },
    {
        "id": "parent",
        "name": "Parent",
        "custom": False,
        "orderable": False,
        "navigable": True,
        "searchable": False,
        "clauseNames": ["parent"],
        "schema": {"type": "issuelink", "system": "parent"},
    },
]


@router.get("/field")
async def list_fields(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all fields (system + custom)."""
    # Start with a copy of system fields
    all_fields = list(SYSTEM_FIELDS)

    # Fetch custom fields from the database
    result = await db.execute(select(CustomField).order_by(CustomField.field_id))
    custom_fields = list(result.scalars().all())

    # Map custom field types to Jira schema types
    type_map = {
        "string": "string",
        "text": "string",
        "number": "number",
        "float": "number",
        "date": "date",
        "datetime": "datetime",
        "select": "option",
        "multiselect": "array",
        "user": "user",
        "url": "string",
    }

    for cf in custom_fields:
        schema_type = type_map.get(cf.field_type, "string")
        schema: dict = {"type": schema_type, "custom": cf.field_id, "customId": cf.id}

        if cf.field_type == "multiselect":
            schema["items"] = "option"

        all_fields.append({
            "id": cf.field_id,
            "name": cf.name,
            "custom": True,
            "orderable": True,
            "navigable": True,
            "searchable": True,
            "clauseNames": [cf.name, f"cf[{cf.id}]"],
            "schema": schema,
        })

    return all_fields
