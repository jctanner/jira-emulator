"""Jira Cloud behaviour mirrored by the emulator (CC-63 audit).

See ``docs/plans/jira-cloud-behaviour-audit-2026-11.md`` for the sources.
Every behaviour is checked on REST v2 and v3.
"""

import httpx
import pytest

from tests.conftest import AUTH_HEADER

VERSIONS = pytest.mark.parametrize("v", [2, 3])


async def _issue(client: httpx.AsyncClient, summary: str, **fields) -> dict:
    body = {
        "fields": {
            "project": {"key": fields.pop("project", "RHOAIENG")},
            "summary": summary,
            "issuetype": {"name": fields.pop("issuetype", "Bug")},
            **fields,
        }
    }
    resp = await client.post("/rest/api/2/issue", json=body, headers=AUTH_HEADER)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _keys(client: httpx.AsyncClient, v: int, jql: str) -> set[str]:
    """All keys matching *jql*, walking /search/jql pages."""
    keys: set[str] = set()
    token = None
    while True:
        body = {"jql": jql, "fields": ["key"], "maxResults": 2}
        if token:
            body["nextPageToken"] = token
        resp = await client.post(f"/rest/api/{v}/search/jql", json=body, headers=AUTH_HEADER)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        keys.update(i["key"] for i in data["issues"])
        if data["isLast"]:
            return keys
        token = data["nextPageToken"]


# ---------------------------------------------------------------------------
# F1: != and NOT IN never match an empty field
# ---------------------------------------------------------------------------


@pytest.fixture
async def labelled(client):
    """Three RHAIRFE issues: no labels, an ignored label, an unrelated label."""
    none = await _issue(client, "no labels", project="RHAIRFE", issuetype="Feature Request")
    ignored = await _issue(
        client, "ignored", project="RHAIRFE", issuetype="Feature Request", labels=["rfe-creator-ignore"]
    )
    other = await _issue(client, "other", project="RHAIRFE", issuetype="Feature Request", labels=["triage"])
    return none["key"], ignored["key"], other["key"]


@VERSIONS
async def test_labels_not_in_excludes_unlabelled(client, labelled, v):
    none, ignored, other = labelled
    # The rfe-autofix discovery clause (breadboard src/cli/phases.py).
    jql = "project = RHAIRFE AND labels not in (rfe-creator-ignore, rfe-creator-autofix-rubric-pass)"
    assert await _keys(client, v, jql) == {other}


@VERSIONS
async def test_labels_not_in_or_empty_includes_unlabelled(client, labelled, v):
    none, ignored, other = labelled
    jql = "project = RHAIRFE AND (labels not in (rfe-creator-ignore) OR labels is EMPTY)"
    assert await _keys(client, v, jql) == {none, other}


@VERSIONS
async def test_labels_ne_excludes_unlabelled(client, labelled, v):
    none, ignored, other = labelled
    assert await _keys(client, v, "project = RHAIRFE AND labels != rfe-creator-ignore") == {other}


@VERSIONS
async def test_labels_eq_and_in_empty_keyword(client, labelled, v):
    none, ignored, other = labelled
    assert await _keys(client, v, "project = RHAIRFE AND labels = EMPTY") == {none}
    assert await _keys(client, v, "project = RHAIRFE AND labels != EMPTY") == {ignored, other}
    assert await _keys(client, v, "project = RHAIRFE AND labels in (triage, EMPTY)") == {none, other}


@VERSIONS
async def test_labels_stay_exact_and_case_insensitive(client, labelled, v):
    none, ignored, other = labelled
    # No substring matching: "rfe-creator" is not "rfe-creator-ignore".
    assert await _keys(client, v, "project = RHAIRFE AND labels = rfe-creator") == set()
    assert await _keys(client, v, "project = RHAIRFE AND labels = TRIAGE") == {other}
    resp = await client.post(
        f"/rest/api/{v}/search/jql", json={"jql": "labels ~ triage", "fields": ["key"]}, headers=AUTH_HEADER
    )
    assert resp.status_code == 400


@VERSIONS
async def test_component_and_versions_not_in_exclude_empty(client, v):
    comp = await client.post(
        "/rest/api/2/component", json={"name": "Dashboard", "project": "RHOAIENG"}, headers=AUTH_HEADER
    )
    assert comp.status_code == 201, comp.text
    await client.post("/rest/api/2/component", json={"name": "Pipelines", "project": "RHOAIENG"}, headers=AUTH_HEADER)
    ver = await client.post("/rest/api/2/version", json={"name": "2.0", "project": "RHOAIENG"}, headers=AUTH_HEADER)
    assert ver.status_code == 201, ver.text
    await client.post("/rest/api/2/version", json={"name": "3.0", "project": "RHOAIENG"}, headers=AUTH_HEADER)

    bare = await _issue(client, "bare")
    tagged = await _issue(
        client,
        "tagged",
        components=[{"name": "Pipelines"}],
        fixVersions=[{"name": "3.0"}],
        versions=[{"name": "3.0"}],
    )

    assert await _keys(client, v, "project = RHOAIENG AND component != Dashboard") == {tagged["key"]}
    assert await _keys(client, v, "project = RHOAIENG AND component not in (Dashboard)") == {tagged["key"]}
    assert await _keys(client, v, "project = RHOAIENG AND fixVersion not in (2.0)") == {tagged["key"]}
    assert await _keys(client, v, "project = RHOAIENG AND affectedVersion != 2.0") == {tagged["key"]}
    assert await _keys(client, v, "project = RHOAIENG AND affectedVersion is EMPTY") == {bare["key"]}


@VERSIONS
async def test_custom_field_ne_excludes_empty(client, v):
    await _issue(client, "no value")
    has = await _issue(client, "has value", customfield_40001="beta")
    assert await _keys(client, v, "project = RHOAIENG AND customfield_40001 != alpha") == {has["key"]}
    assert await _keys(client, v, "project = RHOAIENG AND cf[40001] not in (alpha)") == {has["key"]}


# ---------------------------------------------------------------------------
# F2: /search/jql is Jira Cloud's enhanced search on v2 and v3
# ---------------------------------------------------------------------------


@VERSIONS
async def test_search_jql_response_shape(client, v):
    for i in range(3):
        await _issue(client, f"shape {i}")
    resp = await client.post(
        f"/rest/api/{v}/search/jql", json={"jql": "project = RHOAIENG", "maxResults": 2}, headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"issues", "isLast", "nextPageToken"}
    assert data["isLast"] is False
    # Default fields are ids only.
    assert all(set(issue) == {"id"} for issue in data["issues"])

    last = await client.post(
        f"/rest/api/{v}/search/jql",
        json={"jql": "project = RHOAIENG", "maxResults": 2, "nextPageToken": data["nextPageToken"]},
        headers=AUTH_HEADER,
    )
    page = last.json()
    assert page["isLast"] is True
    assert "nextPageToken" not in page
    assert len(page["issues"]) == 1


@VERSIONS
async def test_search_jql_exact_page_boundary_is_last(client, v):
    for i in range(2):
        await _issue(client, f"boundary {i}")
    data = (
        await client.post(
            f"/rest/api/{v}/search/jql", json={"jql": "project = RHOAIENG", "maxResults": 2}, headers=AUTH_HEADER
        )
    ).json()
    assert data["isLast"] is True
    assert len(data["issues"]) == 2


@VERSIONS
async def test_search_jql_get_with_fields_and_expand(client, v):
    created = await _issue(client, "get fields")
    resp = await client.get(
        f"/rest/api/{v}/search/jql",
        params=[("jql", "project = RHOAIENG"), ("fields", "summary,status"), ("fields", "labels"), ("expand", "names")],
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200, resp.text
    issue = resp.json()["issues"][0]
    assert issue["key"] == created["key"]
    assert set(issue["fields"]) == {"summary", "status", "labels"}


@VERSIONS
@pytest.mark.parametrize("jql", ["", "   ", "ORDER BY created DESC", "order by key"])
async def test_search_jql_rejects_unbounded(client, v, jql):
    for method in ("post", "get"):
        if method == "post":
            resp = await client.post(f"/rest/api/{v}/search/jql", json={"jql": jql}, headers=AUTH_HEADER)
        else:
            resp = await client.get(f"/rest/api/{v}/search/jql", params={"jql": jql}, headers=AUTH_HEADER)
        assert resp.status_code == 400, (method, resp.text)
        assert "Unbounded JQL" in resp.json()["errorMessages"][0]


@VERSIONS
async def test_search_jql_invalid_token(client, v):
    resp = await client.post(
        f"/rest/api/{v}/search/jql",
        json={"jql": "project = RHOAIENG", "nextPageToken": "not-a-token"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400


@VERSIONS
async def test_legacy_search_keeps_total_and_unbounded_jql(client, v):
    await _issue(client, "legacy")
    resp = await client.post(
        f"/rest/api/{v}/search", json={"jql": "ORDER BY updated DESC", "maxResults": 10}, headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert "fields" in data["issues"][0]


# ---------------------------------------------------------------------------
# F3: POST /search/approximate-count
# ---------------------------------------------------------------------------


@VERSIONS
async def test_approximate_count(client, v):
    for i in range(3):
        await _issue(client, f"count {i}")
    resp = await client.post(
        f"/rest/api/{v}/search/approximate-count", json={"jql": "project = RHOAIENG"}, headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    assert resp.json() == {"count": 3}

    unbounded = await client.post(
        f"/rest/api/{v}/search/approximate-count", json={"jql": "order by key"}, headers=AUTH_HEADER
    )
    assert unbounded.status_code == 400


# ---------------------------------------------------------------------------
# F4: CHANGE-3440 -- text-field =, IN, NOT IN are exact phrase searches
# ---------------------------------------------------------------------------


@pytest.fixture
async def text_values(client):
    a = await _issue(client, "a", customfield_50001="Very urgent issue")
    b = await _issue(client, "b", customfield_50001="urgent")
    c = await _issue(client, "c", customfield_50001="beta alpha, then gamma")
    d = await _issue(client, "d", customfield_50001="nonurgent")
    return a["key"], b["key"], c["key"], d["key"]


@VERSIONS
async def test_text_field_eq_is_phrase_search(client, text_values, v):
    a, b, c, d = text_values
    # Whole words only: "nonurgent" does not contain the word "urgent".
    assert await _keys(client, v, 'project = RHOAIENG AND cf[50001] = "URGENT"') == {a, b}
    assert await _keys(client, v, 'project = RHOAIENG AND cf[50001] = "very urgent"') == {a}
    # Word order is kept.
    assert await _keys(client, v, 'project = RHOAIENG AND cf[50001] = "alpha beta"') == set()
    assert await _keys(client, v, 'project = RHOAIENG AND cf[50001] = "beta alpha"') == {c}


@VERSIONS
async def test_text_field_in_and_not_in_are_phrase_searches(client, text_values, v):
    a, b, c, d = text_values
    assert await _keys(client, v, 'project = RHOAIENG AND customfield_50001 in ("gamma", "very urgent")') == {a, c}
    assert await _keys(client, v, 'project = RHOAIENG AND customfield_50001 not in ("urgent")') == {c, d}


@VERSIONS
async def test_select_field_eq_stays_whole_value(client, v):
    from sqlalchemy import update

    from jira_emulator.database import get_session_factory
    from jira_emulator.models.custom_field import CustomField

    full = await _issue(client, "select", customfield_50002="Very urgent")
    # A select-type field (as configured by config import) keeps exact
    # whole-value matching; CHANGE-3440 covers text fields only.
    async with get_session_factory()() as session:
        await session.execute(
            update(CustomField).where(CustomField.field_id == "customfield_50002").values(field_type="select")
        )
        await session.commit()
    assert await _keys(client, v, 'project = RHOAIENG AND cf[50002] = "urgent"') == set()
    assert await _keys(client, v, 'project = RHOAIENG AND cf[50002] = "very urgent"') == {full["key"]}


# ---------------------------------------------------------------------------
# F5: "work item" and "space" JQL aliases
# ---------------------------------------------------------------------------


@VERSIONS
async def test_work_item_and_space_aliases(client, v):
    bug = await _issue(client, "alias bug")
    story = await _issue(client, "alias story", issuetype="Story")
    key = bug["key"]
    assert await _keys(client, v, "space = RHOAIENG") == {key, story["key"]}
    assert await _keys(client, v, "space = RHOAIENG AND workType = Story") == {story["key"]}
    assert await _keys(client, v, f"workItemKey = {key}") == {key}
    assert await _keys(client, v, f"workItem in ({key}, {story['key']})") == {key, story["key"]}
    assert await _keys(client, v, f"id = {bug['id']}") == {key}
    assert await _keys(client, v, f"issuekey = {key.lower()}") == {key}
    resp = await client.post(
        f"/rest/api/{v}/search/jql",
        json={"jql": "space = RHOAIENG ORDER BY workItemKey DESC", "fields": ["key"]},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# F6: GET /label
# ---------------------------------------------------------------------------


@VERSIONS
async def test_label_list_prefix_and_paging(client, v):
    await _issue(client, "l1", labels=["strat-creator-rubric-pass", "Security"])
    await _issue(client, "l2", labels=["strat-creator-rubric-pass", "performance"])

    data = (await client.get(f"/rest/api/{v}/label", headers=AUTH_HEADER)).json()
    assert data["values"] == sorted(["Security", "performance", "strat-creator-rubric-pass"])
    assert data["total"] == 3
    assert data["isLast"] is True

    page = (
        await client.get(f"/rest/api/{v}/label", params={"maxResults": 1, "startAt": 1}, headers=AUTH_HEADER)
    ).json()
    assert page["values"] == [data["values"][1]]
    assert page["isLast"] is False

    # query is a case-insensitive prefix, not a substring.
    pref = (await client.get(f"/rest/api/{v}/label", params={"query": "STRAT"}, headers=AUTH_HEADER)).json()
    assert pref["values"] == ["strat-creator-rubric-pass"]
    sub = (await client.get(f"/rest/api/{v}/label", params={"query": "rubric"}, headers=AUTH_HEADER)).json()
    assert sub["values"] == []
    # LIKE wildcards in the query are literal.
    wild = (await client.get(f"/rest/api/{v}/label", params={"query": "%"}, headers=AUTH_HEADER)).json()
    assert wild["values"] == []
