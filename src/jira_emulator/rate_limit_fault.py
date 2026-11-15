"""Optional rate-limit fault injection with Jira Cloud's 429 headers.

Jira Cloud has enforced points-based and burst rate limits since 2026-03-02
(CHANGE-2958, CHANGE-3003, CHANGE-3045). See
https://developer.atlassian.com/cloud/jira/platform/rate-limiting/.

This is off unless ``RATE_LIMIT_FAULT`` is set. Its value is a
comma-separated list of ``key=value`` options:

``reason``
    The ``RateLimit-Reason`` to send: ``jira-quota-global-based`` (the
    default), ``jira-quota-tenant-based``, ``jira-burst-based`` or
    ``jira-per-issue-on-write``.
``every``
    Reject every Nth matching request, counting from the first. The
    default, 1, rejects them all.
``methods``
    HTTP methods to match, separated by ``|``, for example ``POST|PUT``.
    The default matches every method.
``path``
    Only match request paths that start with this prefix, as sent by the
    client (``/rest/api/3/...`` stays v3). The default is ``/rest/``.
``retry_after``
    Seconds for ``Retry-After``, ``X-RateLimit-Reset`` and ``RateLimit``'s
    ``t``. The default is 60.

For example, ``RATE_LIMIT_FAULT=reason=jira-burst-based,every=3,methods=POST``
rejects every third POST under ``/rest/`` as a burst-limit 429.

Matching requests that are not rejected also carry ``RateLimit-Policy`` and
``RateLimit``, as Jira's do. Requests that do not match are left alone.
"""

import itertools
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REASONS = (
    "jira-quota-global-based",
    "jira-quota-tenant-based",
    "jira-burst-based",
    "jira-per-issue-on-write",
)

# The policy each reason is reported under, with its quota and window. The
# quotas and windows are the documented examples: 65000 points an hour, and
# 100 requests a second for a burst. Jira documents no named policy for the
# per-issue write limit, so that reason sends no policy headers.
_POLICIES: dict[str, tuple[str, int, int]] = {
    "jira-quota-global-based": ("global-app-quota", 65000, 3600),
    "jira-quota-tenant-based": ("tenant-app-quota", 65000, 3600),
    "jira-burst-based": ("jira-burst-based", 100, 1),
}

ERROR_MESSAGE = "Rate limit exceeded."


@dataclass(frozen=True)
class FaultRule:
    reason: str = "jira-quota-global-based"
    every: int = 1
    methods: frozenset[str] = frozenset()
    path: str = "/rest/"
    retry_after: int = 60

    @classmethod
    def parse(cls, spec: str) -> "FaultRule":
        """Parse a ``RATE_LIMIT_FAULT`` value; raise ``ValueError`` if it is invalid."""
        options: dict = {}
        for part in filter(None, (p.strip() for p in spec.split(","))):
            key, sep, value = part.partition("=")
            key, value = key.strip(), value.strip()
            if not sep or not value:
                raise ValueError(f"RATE_LIMIT_FAULT: expected key=value, got {part!r}")
            if key == "reason":
                if value not in REASONS:
                    raise ValueError(f"RATE_LIMIT_FAULT: reason must be one of {', '.join(REASONS)}")
                options["reason"] = value
            elif key in ("every", "retry_after"):
                number = int(value)
                if number < 1:
                    raise ValueError(f"RATE_LIMIT_FAULT: {key} must be at least 1")
                options[key] = number
            elif key == "methods":
                options["methods"] = frozenset(m.strip().upper() for m in value.split("|") if m.strip())
            elif key == "path":
                options["path"] = value
            else:
                raise ValueError(f"RATE_LIMIT_FAULT: unknown option {key!r}")
        return cls(**options)

    def matches(self, method: str, path: str) -> bool:
        return path.startswith(self.path) and (not self.methods or method.upper() in self.methods)

    def policy_headers(self, remaining: int | None) -> list[tuple[bytes, bytes]]:
        policy = _POLICIES.get(self.reason)
        if policy is None:
            return []
        name, quota, window = policy
        state = f'"{name}";' + (f"r={remaining};" if remaining is not None else "") + f"t={self.retry_after}"
        return [
            (b"ratelimit-policy", f'"{name}";q={quota};w={window}'.encode()),
            (b"ratelimit", state.encode()),
        ]

    def rejection_headers(self, now: datetime) -> list[tuple[bytes, bytes]]:
        reset = (now + timedelta(seconds=self.retry_after)).strftime("%Y-%m-%dT%H:%M:%SZ")
        policy = _POLICIES.get(self.reason)
        headers = [
            (b"retry-after", str(self.retry_after).encode()),
            (b"x-ratelimit-reset", reset.encode()),
            (b"ratelimit-reason", self.reason.encode()),
            (b"x-ratelimit-remaining", b"0"),
        ]
        if policy is not None:
            headers.append((b"x-ratelimit-limit", str(policy[1]).encode()))
        return headers + self.policy_headers(remaining=0)


class RateLimitFaultMiddleware:
    """ASGI middleware that rejects matching requests as Jira Cloud would."""

    def __init__(self, app: ASGIApp, rule: FaultRule):
        self.app = app
        self.rule = rule
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.rule.matches(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return
        with self._lock:
            number = next(self._counter)
        if (number - 1) % self.rule.every == 0:
            body = json.dumps({"errorMessages": [ERROR_MESSAGE], "errors": {}}).encode()
            headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *self.rule.rejection_headers(datetime.now(UTC)),
            ]
            await send({"type": "http.response.start", "status": 429, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_policy(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), *self.rule.policy_headers(None)]}
            await send(message)

        await self.app(scope, receive, send_with_policy)
