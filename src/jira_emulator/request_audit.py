"""Request audit: a bounded, in-memory record of write requests to the REST API.

Test harnesses use it to check exactly what a client wrote, for example that a
run touched only the issues it was given.  Every non-GET request under
``/rest/`` is recorded with its method, path as the client sent it (``/rest/api/3``
paths stay v3), query string, request body, response status and the user named
by Basic auth.  Admin endpoints (``/api/admin/...``) are not recorded.

Entries carry a sequence number that keeps increasing across ``clear()``, so a
reader can poll with ``since=<last seq>``.  The record lives in process memory
only: it does not survive a restart, and a reset or snapshot restore leaves it
alone.  Read it with ``GET /api/admin/requests`` and empty it with
``DELETE /api/admin/requests``.
"""

import base64
import threading
from collections import deque
from datetime import UTC, datetime

# Methods that do not change state and are not recorded.
_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


class RequestAudit:
    """Thread-safe ring buffer of recorded requests."""

    def __init__(self, max_entries: int, max_body_bytes: int):
        self.max_entries = max_entries
        self.max_body_bytes = max_body_bytes
        self._entries: deque[dict] = deque(maxlen=max_entries or None)
        self._seq = 0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.max_entries > 0

    def add(self, entry: dict) -> None:
        with self._lock:
            self._seq += 1
            self._entries.append({"seq": self._seq, **entry})

    def since(self, seq: int = 0, limit: int | None = None) -> list[dict]:
        with self._lock:
            entries = [e for e in self._entries if e["seq"] > seq]
        return entries[:limit] if limit else entries

    @property
    def last_seq(self) -> int:
        return self._seq

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def _basic_auth_user(headers: dict[bytes, bytes]) -> str | None:
    """Return the username from a Basic Authorization header, if any."""
    value = headers.get(b"authorization", b"").decode("latin-1")
    if not value.lower().startswith("basic "):
        return None
    try:
        return base64.b64decode(value[6:]).decode("utf-8").split(":", 1)[0]
    except (ValueError, UnicodeDecodeError):
        return None


class RequestAuditMiddleware:
    """ASGI middleware that records write requests into a ``RequestAudit``.

    Install it outermost, so it sees the path before the v3-to-v2 rewrite.
    It passes the body through unchanged while keeping a capped copy.
    """

    def __init__(self, app, audit: RequestAudit):
        self.app = app
        self.audit = audit

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or not self.audit.enabled
            or scope["method"] in _READ_METHODS
            or not scope["path"].startswith("/rest/")
        ):
            await self.app(scope, receive, send)
            return

        method, path = scope["method"], scope["path"]
        query = scope.get("query_string", b"").decode("latin-1")
        headers = dict(scope.get("headers", []))
        body = bytearray()
        size = 0
        status = None

        async def recording_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                size += len(chunk)
                room = self.audit.max_body_bytes - len(body)
                if room > 0:
                    body.extend(chunk[:room])
            return message

        async def recording_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        received = datetime.now(tz=UTC)
        try:
            await self.app(scope, recording_receive, recording_send)
        finally:
            self.audit.add(
                {
                    "time": received.isoformat(timespec="milliseconds"),
                    "method": method,
                    "path": path,
                    "query": query,
                    "status": status,
                    "user": _basic_auth_user(headers),
                    "content_type": headers.get(b"content-type", b"").decode("latin-1"),
                    "body_bytes": size,
                    "body_truncated": size > len(body),
                    "body": body.decode("utf-8", errors="replace"),
                }
            )
