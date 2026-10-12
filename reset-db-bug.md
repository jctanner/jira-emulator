# Jira emulator admin reset failure

## Reproduction

With the current `podman-compose` stack running:

```bash
podman exec adlc-workflow_claude_1 \
  sh -lc 'curl --fail-with-body --silent --show-error \
    -X POST "$ADLC_JIRA_URL/api/admin/reset" \
    -H "Authorization: Bearer $ADLC_JIRA_TOKEN" \
    -H "Accept: application/json"'
```

The endpoint returns HTTP 500. The ADLC batch helper is intended to use this
endpoint before seeding its ten test RFEs, so the failure currently prevents
the batch test from reaching the workflow.

## Observed traceback

The emulator log ends with:

```text
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
[SQL: DROP TABLE webhook_outbox]
```

The failure occurs in:

```text
jira_emulator/routers/admin.py:210 reset_database
  await conn.run_sync(Base.metadata.drop_all)
```

## Likely cause

The webhook feature added a background delivery worker in
`jira_emulator/app.py`. The worker is enabled for the compose configuration
because the database is file-backed SQLite (`sqlite+aiosqlite:////data/jira.db`),
and it continuously opens sessions, claims outbox rows, and updates
`webhook_outbox`.

The admin reset path drops and recreates all tables while that worker and/or
another request session can still hold a SQLite connection/transaction. SQLite
then rejects `DROP TABLE webhook_outbox` with `database is locked`.

The old reset path may have worked before the webhook outbox table and worker
were introduced because there was no background database activity competing
with the destructive DDL.

## Suggested fix direction

Make reset and webhook delivery mutually exclusive. Possible approaches:

1. Add an application-level reset lock shared with the webhook worker and all
   webhook DB operations. Pause/cancel the worker, wait for its session to
   close, perform reset inside a clean transaction, then restart the worker.
2. At minimum, have the reset endpoint stop or quiesce the outbox worker before
   `Base.metadata.drop_all`, and ensure every worker session is closed before
   DDL begins.
3. Add a regression test that enables webhooks with file-backed SQLite, starts
   the app, calls `POST /api/admin/reset`, and asserts HTTP 200 plus the
   presence of the reseeded tables/data.
4. Consider a SQLite busy timeout/WAL configuration as a resilience measure,
   but do not rely on it as the correctness fix for concurrent drop/recreate
   operations.

## Update after commit `9331366`

The rebased fix adds `app.state.database_operation_lock` and uses it around
the webhook worker and the reset endpoint. The remaining race is that ordinary
FastAPI database dependencies still bypass this lock:

```text
src/jira_emulator/database.py:get_db()
```

Every route using `db: AsyncSession = Depends(get_db)` can therefore hold an
independent SQLite session while reset performs `Base.metadata.drop_all`.
The compose healthcheck continuously calls `/rest/api/2/project`, and the
workflow itself issues Jira requests, so either can keep a transaction or
connection active during reset. The new lock does not coordinate those
sessions with reset.

The next fix should either:

- acquire the application database-operation lock in `get_db()` for the full
  request/session lifetime, while avoiding deadlock for reset's own direct
  engine/session work; or
- introduce a reset/quiesce mode that rejects or drains normal DB requests
  before DDL begins, then resumes them after reseeding.

The SQLite engine should also set a suitable `busy_timeout`, but that should be
treated as backoff protection rather than the synchronization mechanism.

## Update after commit `e667426`

The failure still reproduces after the middleware and busy-timeout changes. A
more specific remaining lock source is the reset request's authentication
dependency:

```python
async def reset_database(
    request: Request,
    current_user: User = Depends(get_current_user),
):
```

`get_current_user` depends on the generator dependency `get_db`. FastAPI does
not finalize that dependency until the request has completely finished, so the
authentication session remains alive while `reset_database()` executes
`Base.metadata.drop_all()` and `create_all()`.

The database middleware explicitly bypasses `/api/admin/reset`, and the route
acquires the operation lock only inside the handler. That lock coordinates the
webhook worker and ordinary requests, but it does not release the database
session created for authentication before destructive DDL begins. Reset can
therefore still run SQLite DDL while another connection owns a transaction.

The fix should authenticate reset requests through a path that releases its
database session before destructive DDL, or otherwise quiesce/close all
authentication and request sessions before calling `drop_all()`. Keep the
regression test authenticated, with `WEBHOOKS_ENABLED=true` and a file-backed
SQLite database.

## Relevant files

- `src/jira_emulator/routers/admin.py` — destructive reset endpoint.
- `src/jira_emulator/app.py` — webhook outbox background worker lifecycle.
- `src/jira_emulator/models/webhook.py` — `webhook_outbox` table.
- `src/jira_emulator/services/webhook_service.py` — outbox claim/delivery logic.
- `src/jira_emulator/database.py` — SQLite engine/session configuration.
