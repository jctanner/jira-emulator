"""POST /issue/bulkfetch with Jira Cloud's 100/1000 limits (issue #21)."""

import pytest

from jira_emulator.services.bulkfetch_service import issue_limit

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}
API = ["2", "3"]


async def _create(client, summary):
    resp = await client.post(
        "/rest/api/2/issue",
        json={"fields": {"project": {"key": "TEST"}, "issuetype": {"name": "Task"}, "summary": summary}},
        headers=AUTH,
    )
    assert resp.status_code == 201
    return resp.json()


async def _bulkfetch(client, api, body):
    return await client.post(f"/rest/api/{api}/issue/bulkfetch", json=body, headers=AUTH)


def _keys(count):
    return [f"TEST-{n}" for n in range(1, count + 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize("api", API)
async def test_returns_issues_in_ascending_id_order(client, api):
    first, second, third = [await _create(client, name) for name in ("one", "two", "three")]
    resp = await _bulkfetch(
        client,
        api,
        # Mixed ids and keys, a lower-case key, a duplicate and an unknown key.
        {"issueIdsOrKeys": [third["key"], first["id"], second["key"].lower(), third["id"], "TEST-99999"]},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert [i["key"] for i in data["issues"]] == [first["key"], second["key"], third["key"]]
    assert data["issueErrors"] == []  # unknown issues are left out, not reported
    issue = data["issues"][0]
    assert {"id", "key", "self", "fields", "expand"} <= set(issue)
    assert "changelog" not in issue
    # The default is *navigable.
    assert issue["fields"]["summary"] == "one"
    assert "status" in issue["fields"]
    description = issue["fields"].get("description")
    assert description is None or (api == "3") == isinstance(description, dict)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", API)
async def test_fields_include_exclude_and_properties(client, api):
    issue = await _create(client, "with property")
    put = await client.put(f"/rest/api/{api}/issue/{issue['key']}/properties/ci", json={"run": 7}, headers=AUTH)
    assert put.status_code in (200, 201)

    explicit = (await _bulkfetch(client, api, {"issueIdsOrKeys": [issue["key"]], "fields": ["summary,status"]})).json()
    assert set(explicit["issues"][0]["fields"]) == {"summary", "status"}

    excluded = (
        await _bulkfetch(client, api, {"issueIdsOrKeys": [issue["key"]], "fields": ["*navigable", "-status"]})
    ).json()
    assert "summary" in excluded["issues"][0]["fields"]
    assert "status" not in excluded["issues"][0]["fields"]

    with_props = (
        await _bulkfetch(client, api, {"issueIdsOrKeys": [issue["key"]], "fields": ["summary"], "properties": ["ci"]})
    ).json()
    assert with_props["issues"][0]["properties"] == {"ci": {"run": 7}}

    with_changelog = (
        await _bulkfetch(
            client, api, {"issueIdsOrKeys": [issue["key"]], "fields": ["summary"], "expand": ["changelog"]}
        )
    ).json()
    assert "histories" in with_changelog["issues"][0]["changelog"]


@pytest.mark.asyncio
@pytest.mark.parametrize("api", API)
@pytest.mark.parametrize(
    ("body", "count", "status"),
    [
        ({}, 100, 200),
        ({}, 101, 400),  # default fields are *navigable: limit 100
        ({"fields": ["summary", "status"]}, 1000, 200),
        ({"fields": ["summary"]}, 1001, 400),
        ({"fields": ["*all"]}, 101, 400),
        ({"fields": ["*navigable"]}, 101, 400),
        ({"fields": ["-description"]}, 101, 400),  # exclusions alone are not eligible
        ({"fields": ["summary", "comment"]}, 101, 400),
        ({"fields": ["summary"], "expand": ["names"]}, 1000, 200),
        ({"fields": ["summary"], "expand": ["renderedFields"]}, 101, 400),
        ({"fields": [f"customfield_{n}" for n in range(101)]}, 101, 400),
    ],
)
async def test_issue_limits(client, api, body, count, status):
    resp = await _bulkfetch(client, api, {**body, "issueIdsOrKeys": _keys(count)})
    assert resp.status_code == status, resp.text
    if status == 400:
        assert resp.json()["errorMessages"][0].startswith("A maximum of")


@pytest.mark.asyncio
@pytest.mark.parametrize("api", API)
async def test_rejects_empty_request_and_too_many_properties(client, api):
    empty = await _bulkfetch(client, api, {"issueIdsOrKeys": []})
    assert empty.status_code == 400
    assert "issueIdsOrKeys" in empty.json()["errorMessages"][0]

    props = await _bulkfetch(client, api, {"issueIdsOrKeys": ["TEST-1"], "properties": list("abcdef")})
    assert props.status_code == 400
    assert "5 issue property keys" in props.json()["errorMessages"][0]


def test_issue_limit_rules():
    assert issue_limit(["summary"], []) == 1000
    assert issue_limit(["summary", "-status"], ["schema"]) == 1000
    assert issue_limit(["*navigable"], []) == 100
    assert issue_limit(["summary", "Worklog"], []) == 100
    assert issue_limit(["summary"], ["Transitions"]) == 100
