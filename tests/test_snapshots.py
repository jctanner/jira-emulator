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
