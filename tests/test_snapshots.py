"""Tests for the database snapshot backup & restore service."""

import os
import sqlite3

import pytest

AUTH = {"Authorization": "Basic YWRtaW46YWRtaW4="}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_dirs(tmp_path, monkeypatch):
    """Patch snapshot_service constants to use temp directories."""
    import jira_emulator.services.snapshot_service as ss

    snap_dir = str(tmp_path / "snapshots")
    os.makedirs(snap_dir, exist_ok=True)

    marker = str(tmp_path / "marker")

    monkeypatch.setattr(ss, "SNAPSHOT_DIR", snap_dir)
    monkeypatch.setattr(ss, "CONTAINER_MARKER", marker)

    return {"snap_dir": snap_dir, "marker": marker}


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Create a temp SQLite database and patch settings to point at it."""
    db_path = str(tmp_path / "test.db")

    # Create a real SQLite database with some data
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items (name) VALUES ('hello')")
    conn.commit()
    conn.close()

    # Patch get_settings to return a DATABASE_URL pointing to this file
    from jira_emulator.config import get_settings

    get_settings.cache_clear()

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()

    yield db_path

    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# is_snapshot_enabled
# ---------------------------------------------------------------------------


def test_is_snapshot_enabled_false(tmp_dirs):
    from jira_emulator.services.snapshot_service import is_snapshot_enabled

    assert is_snapshot_enabled() is False


def test_is_snapshot_enabled_true(tmp_dirs):
    from jira_emulator.services.snapshot_service import is_snapshot_enabled

    # Create the marker file
    with open(tmp_dirs["marker"], "w") as f:
        f.write("")

    assert is_snapshot_enabled() is True


# ---------------------------------------------------------------------------
# get_db_path
# ---------------------------------------------------------------------------


def test_get_db_path_file(monkeypatch):
    from jira_emulator.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////data/jira.db")
    get_settings.cache_clear()

    from jira_emulator.services.snapshot_service import get_db_path

    path = get_db_path()
    assert path == "/data/jira.db"

    get_settings.cache_clear()


def test_get_db_path_memory(monkeypatch):
    from jira_emulator.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite://")
    get_settings.cache_clear()

    from jira_emulator.services.snapshot_service import get_db_path

    path = get_db_path()
    assert path is None

    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# create_snapshot / list_snapshots
# ---------------------------------------------------------------------------


def test_create_and_list(tmp_dirs, tmp_db):
    from jira_emulator.services.snapshot_service import create_snapshot, list_snapshots

    info = create_snapshot()

    assert info["name"].startswith("snapshot_")
    assert info["name"].endswith(".db")
    assert info["size_bytes"] > 0
    assert "created" in info

    snapshots = list_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0]["name"] == info["name"]


def test_create_with_label(tmp_dirs, tmp_db):
    from jira_emulator.services.snapshot_service import create_snapshot

    info = create_snapshot(label="my-test")

    assert "my-test" in info["name"]
    assert info["name"].startswith("snapshot_my-test_")


# ---------------------------------------------------------------------------
# delete_snapshot
# ---------------------------------------------------------------------------


def test_delete(tmp_dirs, tmp_db):
    from jira_emulator.services.snapshot_service import (
        create_snapshot,
        delete_snapshot,
        list_snapshots,
    )

    info = create_snapshot()
    assert len(list_snapshots()) == 1

    delete_snapshot(info["name"])
    assert len(list_snapshots()) == 0


def test_delete_nonexistent(tmp_dirs):
    from jira_emulator.services.snapshot_service import delete_snapshot

    with pytest.raises(ValueError, match="not found"):
        delete_snapshot("does_not_exist.db")


# ---------------------------------------------------------------------------
# restore_snapshot
# ---------------------------------------------------------------------------


def test_restore_nonexistent(tmp_dirs, tmp_db):
    from jira_emulator.services.snapshot_service import restore_snapshot

    with pytest.raises(ValueError, match="not found"):
        restore_snapshot("does_not_exist.db")


# ---------------------------------------------------------------------------
# Name validation
# ---------------------------------------------------------------------------


def test_name_validation_slash(tmp_dirs):
    from jira_emulator.services.snapshot_service import delete_snapshot, restore_snapshot

    with pytest.raises(ValueError, match="Invalid"):
        restore_snapshot("../etc/passwd")

    with pytest.raises(ValueError, match="Invalid"):
        delete_snapshot("foo/bar.db")


def test_name_validation_dotdot(tmp_dirs):
    from jira_emulator.services.snapshot_service import delete_snapshot, restore_snapshot

    with pytest.raises(ValueError, match="Invalid"):
        restore_snapshot("..sneaky.db")

    with pytest.raises(ValueError, match="Invalid"):
        delete_snapshot("..sneaky.db")


# ---------------------------------------------------------------------------
# API endpoint — 501 when disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_501_when_disabled(client, monkeypatch):
    """GET /api/admin/snapshots returns 501 when not in container."""
    import jira_emulator.services.snapshot_service as ss

    monkeypatch.setattr(ss, "CONTAINER_MARKER", "/nonexistent/marker")

    resp = await client.get("/api/admin/snapshots", headers=AUTH)
    assert resp.status_code == 501


# ---------------------------------------------------------------------------
# Restore in place, with attachments
# ---------------------------------------------------------------------------


@pytest.fixture()
def attachment_dir(tmp_path, monkeypatch):
    """Point ATTACHMENT_DIR at a temp directory."""
    from jira_emulator.config import get_settings

    path = tmp_path / "attachments"
    path.mkdir()
    monkeypatch.setenv("ATTACHMENT_DIR", str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def _no_subprocess(monkeypatch):
    """Fail the test if restore shells out (the old supervisorctl restart)."""
    import subprocess

    def refuse(*args, **kwargs):
        raise AssertionError(f"restore must not start a process: {args}")

    monkeypatch.setattr(subprocess, "Popen", refuse)


def test_restore_replaces_database_with_open_connection(tmp_dirs, tmp_db, attachment_dir, monkeypatch):
    """Restore writes the live file in place; an open WAL connection sees it."""
    from jira_emulator.services.snapshot_service import create_snapshot, restore_snapshot

    _no_subprocess(monkeypatch)
    live = sqlite3.connect(tmp_db)
    live.execute("PRAGMA journal_mode=WAL")

    info = create_snapshot("before")
    live.execute("INSERT INTO items (name) VALUES ('after-snapshot')")
    live.commit()

    restore_snapshot(info["name"])

    names = [row[0] for row in live.execute("SELECT name FROM items ORDER BY id")]
    live.close()
    assert names == ["hello"]


def test_snapshot_round_trips_attachments(tmp_dirs, tmp_db, attachment_dir):
    from jira_emulator.services.snapshot_service import create_snapshot, list_snapshots, restore_snapshot

    (attachment_dir / "1_strategy.md").write_text("v1")
    info = create_snapshot()
    assert info["includes_attachments"] is True
    assert info["attachment_files"] == 1
    assert list_snapshots()[0]["includes_attachments"] is True

    # Later activity: the file changes and a new upload reuses id 2.
    (attachment_dir / "1_strategy.md").write_text("v2")
    (attachment_dir / "2_extra.md").write_text("new")

    result = restore_snapshot(info["name"])

    assert result["attachments_restored"] is True
    assert sorted(p.name for p in attachment_dir.iterdir()) == ["1_strategy.md"]
    assert (attachment_dir / "1_strategy.md").read_text() == "v1"


def test_restore_legacy_snapshot_keeps_attachments(tmp_dirs, tmp_db, attachment_dir):
    """A database-only snapshot (made before attachments were included) leaves files alone."""
    import shutil

    from jira_emulator.services.snapshot_service import create_snapshot, restore_snapshot

    info = create_snapshot()
    shutil.rmtree(os.path.join(tmp_dirs["snap_dir"], info["name"] + ".attachments"))
    (attachment_dir / "1_keep.md").write_text("keep")

    result = restore_snapshot(info["name"])

    assert result["attachments_restored"] is False
    assert (attachment_dir / "1_keep.md").read_text() == "keep"


def test_delete_removes_attachment_copy(tmp_dirs, tmp_db, attachment_dir):
    from jira_emulator.services.snapshot_service import create_snapshot, delete_snapshot

    (attachment_dir / "1_a.md").write_text("a")
    info = create_snapshot()
    copy = os.path.join(tmp_dirs["snap_dir"], info["name"] + ".attachments")
    assert os.path.isdir(copy)

    delete_snapshot(info["name"])

    assert not os.path.exists(copy)


@pytest.fixture()
async def file_client(tmp_path, tmp_dirs, attachment_dir, monkeypatch):
    """An app client on a file-backed database with snapshots enabled."""
    import httpx

    from jira_emulator.config import get_settings
    from jira_emulator.database import reset_engine

    open(tmp_dirs["marker"], "w").close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'live.db'}")
    monkeypatch.setenv("WEBHOOKS_ENABLED", "false")
    get_settings.cache_clear()
    reset_engine()

    from jira_emulator.app import create_app, lifespan

    app = create_app()
    async with (
        lifespan(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as ac,
    ):
        yield ac

    from jira_emulator.database import get_engine

    await get_engine().dispose()
    reset_engine()
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["2", "3"])
async def test_api_restore_is_live_when_it_returns(file_client, monkeypatch, api):
    """POST .../restore returns with the snapshot's issues and attachments already served."""
    _no_subprocess(monkeypatch)
    base = f"/rest/api/{api}"
    fields = {"project": {"key": "TEST"}, "summary": "kept", "issuetype": {"name": "Task"}}
    kept = (await file_client.post(f"{base}/issue", json={"fields": fields}, headers=AUTH)).json()["key"]
    files = {"file": ("strategy.md", b"v1", "text/markdown")}
    att = await file_client.post(
        f"{base}/issue/{kept}/attachments", files=files, headers={**AUTH, "X-Atlassian-Token": "no-check"}
    )
    assert att.status_code == 200, att.text
    att_id = att.json()[0]["id"]

    snap = await file_client.post("/api/admin/snapshots", json={"label": "api"}, headers=AUTH)
    assert snap.status_code == 201
    name = snap.json()["name"]

    fields = {**fields, "summary": "after snapshot"}
    later = (await file_client.post(f"{base}/issue", json={"fields": fields}, headers=AUTH)).json()["key"]

    resp = await file_client.post(f"/api/admin/snapshots/{name}/restore", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["attachments_restored"] is True

    assert (await file_client.get(f"{base}/issue/{later}", headers=AUTH)).status_code == 404
    assert (await file_client.get(f"{base}/issue/{kept}", headers=AUTH)).status_code == 200
    content = await file_client.get(f"{base}/attachment/content/{att_id}", headers=AUTH)
    assert content.status_code == 200
    assert content.content == b"v1"
