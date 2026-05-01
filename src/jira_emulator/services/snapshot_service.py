"""Database snapshot backup & restore service.

This feature is only available inside the container (where supervisord manages
the jira-api process).  The container is identified by the presence of a marker
file created in the Dockerfile.
"""

import os
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime

from jira_emulator.config import get_settings

CONTAINER_MARKER = "/etc/jira-emulator-container"
SNAPSHOT_DIR = "/data/snapshots"


def is_snapshot_enabled() -> bool:
    """Return True when running inside the managed container."""
    return os.path.exists(CONTAINER_MARKER)


def get_db_path() -> str | None:
    """Extract the file path from the configured DATABASE_URL.

    Returns None for in-memory databases.
    """
    settings = get_settings()
    url = settings.DATABASE_URL

    # Strip the SQLAlchemy dialect prefix
    # e.g. "sqlite+aiosqlite:////data/jira.db" -> "///data/jira.db"
    if ":///" in url:
        path_part = url.split(":///", 1)[1]
    else:
        return None

    # ":memory:" or empty means in-memory
    if not path_part or path_part == ":memory:":
        return None

    # Handle both "///" (absolute) and relative paths
    # "sqlite+aiosqlite:////data/jira.db" -> path_part = "/data/jira.db"
    # "sqlite+aiosqlite:///data/jira.db"  -> path_part = "data/jira.db"
    return path_part


def list_snapshots() -> list[dict]:
    """List existing snapshots, newest first."""
    if not os.path.isdir(SNAPSHOT_DIR):
        return []

    snapshots = []
    for entry in os.listdir(SNAPSHOT_DIR):
        if not entry.endswith(".db"):
            continue
        full = os.path.join(SNAPSHOT_DIR, entry)
        stat = os.stat(full)
        snapshots.append(
            {
                "name": entry,
                "created": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                "size_bytes": stat.st_size,
            }
        )

    snapshots.sort(key=lambda s: s["created"], reverse=True)
    return snapshots


def create_snapshot(label: str | None = None) -> dict:
    """Create a consistent snapshot of the database using sqlite3 backup API."""
    db_path = get_db_path()
    if db_path is None:
        raise RuntimeError("Cannot snapshot an in-memory database")

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    if label:
        # Sanitise label for use in filename
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        filename = f"snapshot_{safe_label}_{ts}.db"
    else:
        filename = f"snapshot_{ts}.db"

    dest = os.path.join(SNAPSHOT_DIR, filename)

    source_conn = sqlite3.connect(db_path)
    target_conn = sqlite3.connect(dest)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()

    stat = os.stat(dest)
    return {
        "name": filename,
        "created": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        "size_bytes": stat.st_size,
    }


def _validate_name(name: str) -> None:
    """Reject path-traversal attempts."""
    if "/" in name or ".." in name:
        raise ValueError(f"Invalid snapshot name: {name}")


def restore_snapshot(name: str) -> None:
    """Restore a snapshot over the live database and restart the API process."""
    _validate_name(name)

    snap_path = os.path.join(SNAPSHOT_DIR, name)
    if not os.path.exists(snap_path):
        raise ValueError(f"Snapshot not found: {name}")

    db_path = get_db_path()
    if db_path is None:
        raise RuntimeError("Cannot restore to an in-memory database")

    shutil.copy2(snap_path, db_path)

    # Fire-and-forget: supervisorctl will kill the current process
    subprocess.Popen(["supervisorctl", "restart", "jira-api"])


def delete_snapshot(name: str) -> None:
    """Delete a snapshot file."""
    _validate_name(name)

    snap_path = os.path.join(SNAPSHOT_DIR, name)
    if not os.path.exists(snap_path):
        raise ValueError(f"Snapshot not found: {name}")

    os.remove(snap_path)
