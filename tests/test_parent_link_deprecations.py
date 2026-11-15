"""Jira Cloud's removal of the Epic Link / Parent Link fields and link types.

- CHANGE-2401: the Epic Link and Parent Link fields are gone from REST;
  ``parent`` replaces both (issue #23).
- CHANGE-2398: ``POST /issueLink`` rejects the Epic and Sub-task link types;
  set the child's ``parent`` instead (issue #24).
"""

import pytest
from sqlalchemy import func, select

from jira_emulator.database import get_session_factory
from jira_emulator.models.link import IssueLink, IssueLinkType
from jira_emulator.routers.links import PARENT_LINK_TYPE_MESSAGE

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}
REMOVED_FIELD_NAMES = {"epic link", "parent link"}


async def _create(client, api, issuetype="Story", parent=None):
    fields = {"project": {"key": "TEST"}, "issuetype": {"name": issuetype}, "summary": issuetype}
    if parent:
        fields["parent"] = {"key": parent}
    resp = await client.post(f"/rest/api/{api}/issue", json={"fields": fields}, headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()["key"]


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
async def test_field_list_has_parent_but_no_epic_or_parent_link(client, api):
    fields = (await client.get(f"/rest/api/{api}/field", headers=AUTH)).json()
    names = {f["name"].casefold() for f in fields}
    assert not names & REMOVED_FIELD_NAMES
    assert "parent" in {f["id"] for f in fields}


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
async def test_issue_uses_parent_not_epic_or_parent_link(client, api):
    epic = await _create(client, api, "Epic")
    story = await _create(client, api, "Story", parent=epic)

    data = (await client.get(f"/rest/api/{api}/issue/{story}?fields=*all", headers=AUTH)).json()
    assert data["fields"]["parent"]["key"] == epic
    # Map each returned field id to its /field name: none is Epic Link or Parent Link.
    fields = (await client.get(f"/rest/api/{api}/field", headers=AUTH)).json()
    names = {f["id"]: f["name"].casefold() for f in fields}
    assert data["fields"], "expected the issue's fields"
    assert not {names.get(field_id, field_id.casefold()) for field_id in data["fields"]} & REMOVED_FIELD_NAMES


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
@pytest.mark.parametrize("type_name", ["Epic-Story Link", "jira_subtask_link"])
async def test_issue_link_rejects_epic_and_subtask_link_types(client, api, type_name):
    # The emulator seeds neither type; add it the way an import would.
    async with get_session_factory()() as db:
        db.add(IssueLinkType(name=type_name, inward_description="is child of", outward_description="is parent of"))
        await db.commit()
    parent = await _create(client, api, "Epic")
    child = await _create(client, api, "Story")

    resp = await client.post(
        f"/rest/api/{api}/issueLink",
        json={"type": {"name": type_name.upper()}, "inwardIssue": {"key": parent}, "outwardIssue": {"key": child}},
        headers=AUTH,
    )

    assert resp.status_code == 400
    assert PARENT_LINK_TYPE_MESSAGE in resp.text
    async with get_session_factory()() as db:
        assert (await db.execute(select(func.count()).select_from(IssueLink))).scalar_one() == 0
