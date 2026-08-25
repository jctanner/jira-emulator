"""Tests for Jira issue-description content-limit behavior."""

import pytest

from jira_emulator.config import Settings, get_settings

LIMIT = 8
AUTH_HEADER = {"Authorization": "Basic YWRtaW46YWRtaW4="}


def _adf(text: str, *, marks: list[dict] | None = None) -> dict:
    text_node = {"type": "text", "text": text}
    if marks:
        text_node["marks"] = marks
    return {
        "version": 1,
        "type": "doc",
        "content": [{"type": "paragraph", "content": [text_node]}],
    }


def _set_limit(limit: int = LIMIT) -> None:
    # The client fixture creates the app before the test body runs, so mutate
    # the cached settings object used by request-time validation.
    get_settings().DESCRIPTION_MAX_LENGTH = limit


def _description_from_response(response: dict, api_version: int) -> str:
    description = response["fields"]["description"]
    if api_version == 2:
        return description
    return description["content"][0]["content"][0]["text"]


def _error_body() -> dict:
    return {"errorMessages": [], "errors": {"description": "CONTENT_LIMIT_EXCEEDED"}}


def test_default_description_limit_is_jira_text_field_limit():
    assert Settings.model_fields["DESCRIPTION_MAX_LENGTH"].default == 32767


@pytest.mark.parametrize("api_version", [2, 3])
async def test_create_description_limit_boundaries(client, api_version: int):
    _set_limit()
    endpoint = f"/rest/api/{api_version}/issue"

    for text, expected_status in [("short", 201), ("12345678", 201), ("123456789", 400)]:
        response = await client.post(
            endpoint,
            json={
                "fields": {
                    "project": {"key": "RHOAIENG"},
                    "issuetype": {"name": "Bug"},
                    "summary": f"Boundary {text}",
                    "description": _adf(text),
                }
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == expected_status
        if expected_status == 400:
            assert response.json() == _error_body()


@pytest.mark.parametrize("api_version", [2, 3])
async def test_update_rejection_preserves_issue_and_history(client, api_version: int):
    _set_limit()
    create_response = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "RHOAIENG"},
                "issuetype": {"name": "Bug"},
                "summary": "Original summary",
                "description": _adf("original"),
            }
        },
        headers=AUTH_HEADER,
    )
    assert create_response.status_code == 201
    key = create_response.json()["key"]

    successful_update = await client.put(
        f"/rest/api/{api_version}/issue/{key}",
        json={"fields": {"description": _adf("updated")}},
        headers=AUTH_HEADER,
    )
    assert successful_update.status_code == 204

    before_response = await client.get(
        f"/rest/api/{api_version}/issue/{key}?expand=changelog",
        headers=AUTH_HEADER,
    )
    before = before_response.json()
    before_history_count = before["changelog"]["total"]
    assert _description_from_response(before, api_version) == "updated"

    rejected_update = await client.put(
        f"/rest/api/{api_version}/issue/{key}",
        json={
            "fields": {
                "summary": "Must not be applied",
                "description": _adf("123456789"),
            }
        },
        headers=AUTH_HEADER,
    )
    assert rejected_update.status_code == 400
    assert rejected_update.json() == _error_body()

    after = (
        await client.get(
            f"/rest/api/{api_version}/issue/{key}?expand=changelog",
            headers=AUTH_HEADER,
        )
    ).json()
    assert after["fields"]["summary"] == "Original summary"
    assert _description_from_response(after, api_version) == "updated"
    assert after["changelog"]["total"] == before_history_count


async def test_limit_counts_normalized_adf_text_not_serialized_json(client):
    _set_limit()
    response = await client.post(
        "/rest/api/3/issue",
        json={
            "fields": {
                "project": {"key": "RHOAIENG"},
                "issuetype": {"name": "Bug"},
                "summary": "ADF normalization",
                "description": _adf(
                    "12345678",
                    marks=[{"type": "link", "attrs": {"href": "https://example.invalid/" * 20}}],
                ),
            }
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201


async def test_description_update_operation_uses_same_limit(client):
    _set_limit()
    create_response = await client.post(
        "/rest/api/2/issue",
        json={
            "fields": {
                "project": {"key": "RHOAIENG"},
                "issuetype": {"name": "Bug"},
                "summary": "Update operation",
            }
        },
        headers=AUTH_HEADER,
    )
    key = create_response.json()["key"]

    response = await client.put(
        f"/rest/api/2/issue/{key}",
        json={"update": {"description": [{"set": _adf("123456789")}]}},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 400
    assert response.json() == _error_body()
