"""A write is committed before its response is sent (read-after-write).

Clients such as strat-creator read a ticket back right after writing it and
treat a stale read as an uncertain write. With request-scoped session
dependencies, FastAPI committed only after the response was sent, so a
client could see its 204 before the change was visible. These tests check,
from a separate SQLite connection at the moment the response starts, that
the change is already committed, on REST v2 and v3.
"""

import sqlite3

import httpx
import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


@pytest.fixture()
async def file_app(tmp_path, monkeypatch):
    """The app on a file-backed database, so another connection can read it."""
    from jira_emulator.config import get_settings
    from jira_emulator.database import get_engine, reset_engine

    db_path = tmp_path / "live.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("WEBHOOKS_ENABLED", "false")
    get_settings.cache_clear()
    reset_engine()

    from jira_emulator.app import create_app, lifespan

    app = create_app()
    async with lifespan(app):
        yield app, db_path
    await get_engine().dispose()
    reset_engine()
    get_settings.cache_clear()


def _committed_labels(db_path, key):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT l.label FROM labels l JOIN issues i ON i.id = l.issue_id WHERE i.key = ?", (key,)
        ).fetchall()
    finally:
        conn.close()
    return sorted(row[0] for row in rows)


@pytest.mark.parametrize("api", ["2", "3"])
async def test_label_update_is_committed_when_the_response_starts(file_app, api, monkeypatch):
    app, db_path = file_app

    # Slow every commit down, so a commit that runs after the response is sent
    # loses the race deterministically instead of only sometimes.
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    real_commit = AsyncSession.commit

    async def slow_commit(self):
        await asyncio.sleep(0.2)
        await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", slow_commit)
    seen_at_start = {}

    async def observing_app(scope, receive, send):
        async def observing_send(message):
            if message["type"] == "http.response.start" and scope.get("method") == "PUT":
                seen_at_start["labels"] = _committed_labels(db_path, seen_at_start["key"])
            await send(message)

        await app(scope, receive, observing_send)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=observing_app), base_url="http://t") as client:
        created = await client.post(
            f"/rest/api/{api}/issue",
            json={"fields": {"project": {"key": "RHOAIENG"}, "summary": "rw", "issuetype": {"name": "Bug"}}},
            headers=AUTH,
        )
        key = seen_at_start["key"] = created.json()["key"]
        resp = await client.put(
            f"/rest/api/{api}/issue/{key}",
            json={"update": {"labels": [{"add": "strat-creator-auto-refined"}]}},
            headers=AUTH,
        )

    assert resp.status_code == 204
    assert seen_at_start["labels"] == ["strat-creator-auto-refined"]
