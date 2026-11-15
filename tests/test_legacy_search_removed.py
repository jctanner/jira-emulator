"""LEGACY_SEARCH=removed: the legacy search APIs return Jira Cloud's 410 (issue #22)."""

import pytest

from jira_emulator.exceptions import LegacyApiRemovedError

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}
REMOVED = [
    ("GET", "/search?jql=project%3DTEST", None),
    ("POST", "/search", {"jql": "project = TEST"}),
    ("POST", "/search/id", {"jql": "project = TEST"}),
    ("POST", "/expression/eval", {"expression": "issue.key"}),
]


@pytest.fixture()
def removed(monkeypatch):
    """Set LEGACY_SEARCH before the ``client`` fixture builds the app."""
    monkeypatch.setenv("LEGACY_SEARCH", "removed")


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
@pytest.mark.parametrize(("method", "path", "body"), REMOVED)
async def test_removed_mode_returns_410(removed, client, api, method, path, body):
    resp = await client.request(method, f"/rest/api/{api}{path}", json=body, headers=AUTH)
    assert resp.status_code == 410
    assert resp.json() == {"errorMessages": [LegacyApiRemovedError.MESSAGE], "errors": {}}


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
async def test_removed_mode_keeps_enhanced_search(removed, client, api):
    jql = await client.post(
        f"/rest/api/{api}/search/jql", json={"jql": "project = TEST", "fields": ["key"]}, headers=AUTH
    )
    assert jql.status_code == 200
    assert "issues" in jql.json()
    count = await client.post(f"/rest/api/{api}/search/approximate-count", json={"jql": "project = TEST"}, headers=AUTH)
    assert count.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
async def test_legacy_search_enabled_by_default(client, api):
    get = await client.get(f"/rest/api/{api}/search?jql=project%3DTEST", headers=AUTH)
    post = await client.post(f"/rest/api/{api}/search", json={"jql": "project = TEST"}, headers=AUTH)
    assert get.status_code == 200
    assert post.status_code == 200
    # The APIs the emulator never implemented stay 404.
    assert (await client.post(f"/rest/api/{api}/search/id", json={}, headers=AUTH)).status_code == 404
    assert (await client.post(f"/rest/api/{api}/expression/eval", json={}, headers=AUTH)).status_code == 404
