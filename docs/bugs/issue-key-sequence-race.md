# Issue key sequence race causes UNIQUE constraint failure

## Status: Fixed

## Symptom

Creating issues in rapid succession against the same project intermittently
fails with HTTP 500:

```
sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) UNIQUE constraint failed: issues.key
[SQL: INSERT INTO issues ("key", ...) VALUES (?, ...)]
[parameters: ('RHAI-3', ...)]
```

The second request allocates the same key as the first because the
`issue_sequences.next_number` read-modify-write is not atomic.

## Reproduction

Observed during the end-to-end demo workflow (`var/demos/end-to-end`). The
`epic_submit` step in `run-epic-decompose.yaml` creates 4 epics in the RHAI
project via `scripts/submit.py` from the `epic-creator` repo.

The reported script runs serially, so the exact trigger in the demo remains to
be confirmed. FastAPI's `get_db()` dependency creates a separate
`AsyncSession` for each request and commits it during dependency cleanup.
Issue-link creation therefore does not share a session with the following
issue creation, and it does not update the issue sequence. The sequence code
is still unsafe when two issue-creation requests for the same project overlap
on separate sessions/connections, but request timing or another issue creator
must be identified to explain this particular observation.

The underlying race was reproduced locally with the normal ASGI test stack by
issuing eight concurrent `POST /rest/api/2/issue` requests for `RHOAIENG`.
Before the fix, the requests allocated `RHOAIENG-1` concurrently and the
second insert raised the same `UNIQUE constraint failed: issues.key` error.

Steps:
1. Reset Jira (delete all projects, re-create with seed data)
2. RHAI project starts with RHAI-1 (bootstrap import)
3. Submit script creates RHAI-2 (E001) — succeeds
4. Submit script creates issue link for RHAI-2
5. Submit script creates RHAI-3 (E002) — succeeds
6. Submit script creates RHAI-3 (E003) — **fails**: key already taken

## Root cause

`src/jira_emulator/services/issue_service.py` lines 219-242:

```python
# -- allocate key --
result = await db.execute(select(IssueSequence).where(IssueSequence.project_id == project.id))
seq = result.scalar_one_or_none()
...
issue_number = seq.next_number          # READ
seq.next_number = issue_number + 1      # MODIFY (in-memory only)
issue_key = f"{project.key}-{issue_number}"
```

The sequence is read via ORM `select`, incremented in Python, and written back
implicitly on the next `flush()`. Between the read and the flush, another
session on a separate connection can read the same `next_number` value,
producing a duplicate key.

The `max_existing` guard (lines 237-239) partially mitigates stale counters by
scanning existing issue keys, but the scan and counter update are separate
operations and do not prevent the race. The missing-sequence path is also
racy: two requests can both observe no row and try to insert the same primary
key.

## Resolution

Issue allocation now uses a single SQLite upsert/update that:

- creates the sequence row safely if it is missing;
- advances a stale sequence to at least one greater than the highest existing
  numeric issue-key suffix for the project;
- reserves the resulting number by incrementing `next_number`; and
- returns the reserved number with `RETURNING`.

The maximum existing suffix is calculated inside that statement. The
stale-counter correction and increment therefore occur in the same write
transaction rather than in a separate scan and update.

SQLite serializes the upsert writes, so separate sessions cannot reserve the
same number. Allocation remains in the issue-creation transaction, so rolling
back issue creation also rolls back the reservation.

## Verification

Regression coverage uses concurrent HTTP POST requests through the local ASGI
test stack and asserts that every request succeeds, all keys are unique, and
the suffixes form the expected sequence. It covers:

- concurrent allocation with an existing sequence row;
- concurrent allocation when the sequence row is missing; and
- stale sequences behind imported issues.

Results after the fix:

- focused issue and import-sequence tests: 16 passed;
- full unit test suite: 198 passed, 16 skipped; and
- concurrent creates allocate unique contiguous keys for both existing and
  missing sequence rows.

The original demo's precise source of overlapping creation remains
unconfirmed, but the independently reproduced allocation failure is fixed.

## Impact

Before the fix, this blocked the end-to-end demo workflow: the `epic_submit`
step failed and aborted the run. Re-running usually worked because
`submit.py` skips already-created epics.
