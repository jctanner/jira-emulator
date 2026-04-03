import pytest
import httpx

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}

async def _create_issue(client, project="RHOAIENG", summary="Test", issuetype="Bug"):
    resp = await client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": project}, "summary": summary, "issuetype": {"name": issuetype}}
    }, headers=AUTH)
    return resp.json()

@pytest.mark.asyncio
async def test_new_issue_has_transitions(client):
    """A new issue should have available transitions."""
    issue = await _create_issue(client)
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}/transitions", headers=AUTH)
    assert resp.status_code == 200
    transitions = resp.json()["transitions"]
    assert len(transitions) >= 1

@pytest.mark.asyncio
async def test_transition_changes_status(client):
    """Performing a transition changes the issue status."""
    issue = await _create_issue(client)

    # Get transitions
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}/transitions", headers=AUTH)
    transitions = resp.json()["transitions"]
    assert len(transitions) > 0

    # Pick first transition
    t_id = transitions[0]["id"]
    target_name = transitions[0]["to"]["name"]

    # Perform transition
    resp = await client.post(f"/rest/api/2/issue/{issue['key']}/transitions", json={
        "transition": {"id": t_id}
    }, headers=AUTH)
    assert resp.status_code == 204

    # Verify status changed
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    assert resp.json()["fields"]["status"]["name"] == target_name

@pytest.mark.asyncio
async def test_invalid_transition_returns_400(client):
    """Performing an invalid transition returns 400."""
    issue = await _create_issue(client)
    resp = await client.post(f"/rest/api/2/issue/{issue['key']}/transitions", json={
        "transition": {"id": "99999"}
    }, headers=AUTH)
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_transition_to_done_sets_resolution(client):
    """Transitioning to a done status auto-sets resolution."""
    issue = await _create_issue(client)

    # Get transitions and find one that goes to a done status
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}/transitions", headers=AUTH)
    transitions = resp.json()["transitions"]

    # Find "Close" transition (goes to Closed which is done category)
    close_transition = None
    for t in transitions:
        if t["to"].get("statusCategory", {}).get("key") == "done":
            close_transition = t
            break

    if close_transition is None:
        pytest.skip("No done transition available from initial status")

    # Perform the transition
    await client.post(f"/rest/api/2/issue/{issue['key']}/transitions", json={
        "transition": {"id": close_transition["id"]}
    }, headers=AUTH)

    # Verify resolution is set
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}", headers=AUTH)
    data = resp.json()
    assert data["fields"]["resolution"] is not None
    assert data["fields"]["resolution"]["name"] == "Done"

@pytest.mark.asyncio
async def test_reopen_from_closed(client):
    """Closing then reopening an issue clears resolution and restores active status."""
    issue = await _create_issue(client)
    key = issue["key"]

    # Close the issue via the global "Close" transition
    resp = await client.get(f"/rest/api/2/issue/{key}/transitions", headers=AUTH)
    transitions = resp.json()["transitions"]
    close_t = next(t for t in transitions if t["to"]["name"] == "Closed")
    resp = await client.post(f"/rest/api/2/issue/{key}/transitions", json={
        "transition": {"id": close_t["id"]}
    }, headers=AUTH)
    assert resp.status_code == 204

    # Verify it's closed with resolution
    resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH)
    data = resp.json()["fields"]
    assert data["status"]["name"] == "Closed"
    assert data["resolution"] is not None

    # Reopen
    resp = await client.get(f"/rest/api/2/issue/{key}/transitions", headers=AUTH)
    transitions = resp.json()["transitions"]
    reopen_t = next(t for t in transitions if t["name"] == "Reopen")
    resp = await client.post(f"/rest/api/2/issue/{key}/transitions", json={
        "transition": {"id": reopen_t["id"]}
    }, headers=AUTH)
    assert resp.status_code == 204

    # Verify it's reopened: active status, resolution cleared
    resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH)
    data = resp.json()["fields"]
    assert data["status"]["name"] == "In Progress"
    assert data["resolution"] is None


@pytest.mark.asyncio
async def test_reopen_from_done(client):
    """An issue completed via Done can be reopened."""
    issue = await _create_issue(client)
    key = issue["key"]

    # Walk: New -> To Do -> In Progress -> Code Review -> Testing -> Done
    steps = ["Start", "Start Progress", "Submit for Review", "Start Testing", "Complete"]
    for step_name in steps:
        resp = await client.get(f"/rest/api/2/issue/{key}/transitions", headers=AUTH)
        transitions = resp.json()["transitions"]
        t = next(t for t in transitions if t["name"] == step_name)
        resp = await client.post(f"/rest/api/2/issue/{key}/transitions", json={
            "transition": {"id": t["id"]}
        }, headers=AUTH)
        assert resp.status_code == 204

    # Verify Done
    resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH)
    assert resp.json()["fields"]["status"]["name"] == "Done"
    assert resp.json()["fields"]["resolution"]["name"] == "Done"

    # Reopen from Done
    resp = await client.get(f"/rest/api/2/issue/{key}/transitions", headers=AUTH)
    transitions = resp.json()["transitions"]
    reopen_t = next(t for t in transitions if t["name"] == "Reopen")
    resp = await client.post(f"/rest/api/2/issue/{key}/transitions", json={
        "transition": {"id": reopen_t["id"]}
    }, headers=AUTH)
    assert resp.status_code == 204

    # Verify reopened
    resp = await client.get(f"/rest/api/2/issue/{key}", headers=AUTH)
    data = resp.json()["fields"]
    assert data["status"]["name"] == "In Progress"
    assert data["resolution"] is None


@pytest.mark.asyncio
async def test_reopen_from_closed_via_v3(client):
    """Reopen works identically through the v3 API path."""
    issue = await _create_issue(client)
    key = issue["key"]

    # Close via v3
    resp = await client.get(f"/rest/api/3/issue/{key}/transitions", headers=AUTH)
    assert resp.status_code == 200
    transitions = resp.json()["transitions"]
    close_t = next(t for t in transitions if t["to"]["name"] == "Closed")
    resp = await client.post(f"/rest/api/3/issue/{key}/transitions", json={
        "transition": {"id": close_t["id"]}
    }, headers=AUTH)
    assert resp.status_code == 204

    # Verify closed via v3
    resp = await client.get(f"/rest/api/3/issue/{key}", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()["fields"]
    assert data["status"]["name"] == "Closed"
    assert data["resolution"] is not None

    # Reopen via v3
    resp = await client.get(f"/rest/api/3/issue/{key}/transitions", headers=AUTH)
    transitions = resp.json()["transitions"]
    reopen_t = next(t for t in transitions if t["name"] == "Reopen")
    resp = await client.post(f"/rest/api/3/issue/{key}/transitions", json={
        "transition": {"id": reopen_t["id"]}
    }, headers=AUTH)
    assert resp.status_code == 204

    # Verify reopened via v3 — description should be ADF, resolution cleared
    resp = await client.get(f"/rest/api/3/issue/{key}", headers=AUTH)
    data = resp.json()["fields"]
    assert data["status"]["name"] == "In Progress"
    assert data["resolution"] is None


@pytest.mark.asyncio
async def test_transition_has_correct_structure(client):
    """Transition response has id, name, to fields."""
    issue = await _create_issue(client)
    resp = await client.get(f"/rest/api/2/issue/{issue['key']}/transitions", headers=AUTH)
    transitions = resp.json()["transitions"]

    for t in transitions:
        assert "id" in t
        assert "name" in t
        assert "to" in t
        assert "name" in t["to"]
        assert "id" in t["to"]
        assert "statusCategory" in t["to"]
