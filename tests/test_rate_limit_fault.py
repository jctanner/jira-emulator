"""Optional 429 fault injection with Jira Cloud's rate-limit headers (issue #20)."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from jira_emulator.rate_limit_fault import ERROR_MESSAGE, FaultRule

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}
ISSUE = {"fields": {"project": {"key": "TEST"}, "issuetype": {"name": "Task"}, "summary": "Rate limited"}}
RATE_LIMIT_HEADERS = {
    "ratelimit-policy",
    "ratelimit",
    "retry-after",
    "x-ratelimit-reset",
    "ratelimit-reason",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
}


@pytest.fixture()
def fault(request, monkeypatch):
    """Set RATE_LIMIT_FAULT before the ``client`` fixture builds the app."""
    monkeypatch.setenv("RATE_LIMIT_FAULT", request.param)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
async def test_no_rate_limit_headers_by_default(client, api):
    resp = await client.post(f"/rest/api/{api}/issue", json=ISSUE, headers=AUTH)
    assert resp.status_code == 201
    assert not RATE_LIMIT_HEADERS & set(resp.headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
@pytest.mark.parametrize(
    "fault", ["reason=jira-burst-based,every=2,methods=POST,path=/rest/api/,retry_after=5"], indirect=True
)
async def test_burst_fault_rejects_every_second_post(fault, client, api):
    before = datetime.now(UTC).replace(microsecond=0)
    rejected = await client.post(f"/rest/api/{api}/issue", json=ISSUE, headers=AUTH)

    assert rejected.status_code == 429
    assert rejected.json() == {"errorMessages": [ERROR_MESSAGE], "errors": {}}
    assert rejected.headers["retry-after"] == "5"
    assert rejected.headers["ratelimit-reason"] == "jira-burst-based"
    assert rejected.headers["x-ratelimit-limit"] == "100"
    assert rejected.headers["x-ratelimit-remaining"] == "0"
    assert rejected.headers["ratelimit-policy"] == '"jira-burst-based";q=100;w=1'
    assert rejected.headers["ratelimit"] == '"jira-burst-based";r=0;t=5'
    reset = rejected.headers["x-ratelimit-reset"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", reset)
    reset_at = datetime.strptime(reset, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert before + timedelta(seconds=5) <= reset_at <= datetime.now(UTC) + timedelta(seconds=5)

    # The retry succeeds and carries the policy headers, but no 429-only headers.
    created = await client.post(f"/rest/api/{api}/issue", json=ISSUE, headers=AUTH)
    assert created.status_code == 201
    assert created.headers["ratelimit-policy"] == '"jira-burst-based";q=100;w=1'
    assert created.headers["ratelimit"] == '"jira-burst-based";t=5'
    assert not {"retry-after", "x-ratelimit-reset", "ratelimit-reason"} & set(created.headers)

    # GET does not match methods=POST and is left alone.
    read = await client.get(f"/rest/api/{api}/issue/{created.json()['key']}", headers=AUTH)
    assert read.status_code == 200
    assert not RATE_LIMIT_HEADERS & set(read.headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["reason=jira-per-issue-on-write,path=/rest/api/3/"], indirect=True)
async def test_per_issue_fault_has_no_policy_and_respects_path(fault, client):
    rejected = await client.post("/rest/api/3/issue", json=ISSUE, headers=AUTH)
    assert rejected.status_code == 429
    assert rejected.headers["ratelimit-reason"] == "jira-per-issue-on-write"
    assert rejected.headers["retry-after"] == "60"
    assert not {"ratelimit-policy", "ratelimit", "x-ratelimit-limit"} & set(rejected.headers)

    # v2 paths do not match the v3 prefix.
    assert (await client.post("/rest/api/2/issue", json=ISSUE, headers=AUTH)).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["every=1"], indirect=True)
async def test_default_reason_is_global_quota_and_rejection_is_audited(fault, client):
    resp = await client.post("/rest/api/2/issue", json=ISSUE, headers=AUTH)
    assert resp.status_code == 429
    assert resp.headers["ratelimit-reason"] == "jira-quota-global-based"
    assert resp.headers["ratelimit-policy"] == '"global-app-quota";q=65000;w=3600'
    # Admin endpoints are outside /rest/ and still work.
    audit = (await client.get("/api/admin/requests", headers=AUTH)).json()
    assert audit["requests"][-1]["status"] == 429


@pytest.mark.parametrize(
    "spec",
    ["reason=jira-made-up", "every=0", "retry_after=-1", "unknown=1", "every", "every=two"],
)
def test_invalid_rules_are_rejected(spec):
    with pytest.raises(ValueError):
        FaultRule.parse(spec)


def test_rule_parsing():
    rule = FaultRule.parse(" reason=jira-quota-tenant-based , every=4, methods=post|Put, path=/rest/api/2/issue ")
    assert rule == FaultRule(
        reason="jira-quota-tenant-based", every=4, methods=frozenset({"POST", "PUT"}), path="/rest/api/2/issue"
    )
    assert rule.matches("PUT", "/rest/api/2/issue/TEST-1")
    assert not rule.matches("GET", "/rest/api/2/issue/TEST-1")
