"""JQL dates: relative dates (-26w, "-1w 2d"), literal dates, the resolved
field, on the v2 and v3 search routes."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from jira_emulator.jql.functions import is_relative_date, relative_date_to_datetime
from jira_emulator.jql.parser import parse_jql

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


async def _create_issue(client, summary, **fields):
    body = {"fields": {"project": {"key": "RHOAIENG"}, "summary": summary, "issuetype": {"name": "Bug"}, **fields}}
    resp = await client.post("/rest/api/2/issue", json=body, headers=AUTH)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["key"]


async def _backdate(key, *, created=None, resolved=None, due=None):
    """The API stamps 'now'; the test needs history."""
    from jira_emulator.database import get_session_factory
    from jira_emulator.models.issue import Issue

    async with get_session_factory()() as session:
        issue = (await session.execute(select(Issue).where(Issue.key == key))).scalar_one()
        if created is not None:
            issue.created_at = created
        if resolved is not None:
            issue.resolved_at = resolved
        if due is not None:
            issue.due_date = due
        await session.commit()


async def _search(client, jql, version=2):
    path = "/rest/api/2/search" if version == 2 else "/rest/api/3/search/jql"
    resp = await client.post(path, json={"jql": jql, "maxResults": 50}, headers=AUTH)
    assert resp.status_code == 200, resp.text
    return {issue["key"] for issue in resp.json()["issues"]}


# -- parser --------------------------------------------------------------


@pytest.mark.parametrize(
    "jql",
    [
        "resolutiondate >= -26w AND statusCategory = Done ORDER BY resolved DESC",
        "created >= +3d",
        "created <= 2w",
        "updated > -30m",
        "created >= -1M AND created <= now()",
    ],
)
def test_relative_dates_parse_unquoted(jql):
    parse_jql(jql)


def test_a_plain_number_is_still_a_number():
    tree = parse_jql("cf[10016] >= 5")
    assert "number_value" in tree.pretty()
    assert "relative_date" not in tree.pretty()


# -- functions -----------------------------------------------------------


def test_relative_date_arithmetic_sums_the_parts():
    now = datetime(2026, 3, 10, 12, 0)
    assert relative_date_to_datetime("-26w", now) == now - timedelta(weeks=26)
    assert relative_date_to_datetime("+3d", now) == now + timedelta(days=3)
    assert relative_date_to_datetime('"-1w 2d"', now) == now - timedelta(weeks=1) + timedelta(days=2)
    assert is_relative_date("-1w 2d") and is_relative_date("2h") and not is_relative_date("2026-01-01")
    with pytest.raises(ValueError):
        relative_date_to_datetime("yesterday", now)


# -- search --------------------------------------------------------------


@pytest.mark.parametrize("version", [2, 3])
async def test_relative_dates_filter_on_created_and_resolved(client, version):
    now = datetime.utcnow()
    recent = await _create_issue(client, "resolved last week")
    old = await _create_issue(client, "resolved last year")
    open_issue = await _create_issue(client, "never resolved")
    await _backdate(recent, created=now - timedelta(days=10), resolved=now - timedelta(days=7))
    await _backdate(old, created=now - timedelta(days=400), resolved=now - timedelta(days=365))
    await _backdate(open_issue, created=now - timedelta(days=3))

    found = await _search(client, "resolutiondate >= -26w", version)
    assert recent in found and old not in found and open_issue not in found

    found = await _search(client, "resolved <= -26w", version)
    assert old in found and recent not in found

    found = await _search(client, "created >= -2w AND created <= -1d", version)
    assert {recent, open_issue} <= found and old not in found

    # The quoted, multi-part form Jira also accepts.
    found = await _search(client, 'created >= "-2w 1d"', version)
    assert {recent, open_issue} <= found and old not in found


async def test_literal_dates_and_day_equality(client):
    on_the_day = await _create_issue(client, "created on the second")
    day_after = await _create_issue(client, "created on the third")
    await _backdate(on_the_day, created=datetime(2026, 3, 2, 15, 30))
    await _backdate(day_after, created=datetime(2026, 3, 3, 0, 5))

    assert on_the_day in await _search(client, "created = 2026-03-02")
    assert day_after not in await _search(client, "created = 2026-03-02")
    assert day_after in await _search(client, 'created != "2026-03-02" AND created < "2026-03-04"')
    assert on_the_day in await _search(client, 'created >= "2026-03-02 15:00" AND created < "2026-03-02 16:00"')
    assert on_the_day not in await _search(client, 'created >= "2026/03/03"')


async def test_due_date_takes_a_date(client):
    soon = await _create_issue(client, "due soon")
    later = await _create_issue(client, "due later")
    await _backdate(soon, due=date.today() + timedelta(days=2))
    await _backdate(later, due=date.today() + timedelta(days=30))
    found = await _search(client, "due <= 7d")
    assert soon in found and later not in found
    found = await _search(client, f"duedate = {(date.today() + timedelta(days=30)).isoformat()}")
    assert later in found and soon not in found


async def test_an_unparseable_date_is_a_bad_request(client):
    resp = await client.post("/rest/api/2/search", json={"jql": "created >= yesterday"}, headers=AUTH)
    assert resp.status_code == 400, resp.text
    assert "Invalid date" in resp.text
