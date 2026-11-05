# A write's response is sent before the write is committed

## Status: Fixed

## Summary

Every route took its session from `get_db` with FastAPI's default
**request** dependency scope. In FastAPI 0.135 the code after a yield
dependency's `yield` runs after `await response(...)` (`fastapi/routing.py`),
so `get_db`'s commit ran *after* the response was sent. And
`DatabaseOperationMiddleware`, a `BaseHTTPMiddleware`, releases its lock as
soon as `call_next` returns.

So a client could receive `204` for a label PUT and read the issue back,
with the next request, before the change was committed.

## Impact

strat-creator's side-effect journal (`strat_side_effects.perform`) reads
every write back and treats a stale read as an uncertain write:

- `push_refined_strategies.py` raised
  `UncertainWrite: add-labels RHAISTRAT-8: server acknowledged but read-back is absent`.
- `release-locks.sh` printed
  `ERROR: remove-labels RHAISTRAT-7: server acknowledged but read-back is absent`
  and left the lock live.

Found by Breadboard's `rhaistrat-initiative-tests` R2 scenario. The failure
was intermittent, in 3 of 4 runs (markovd runs `markov-run-f154914c`,
`markov-run-77b77e9d` and `markov-run-dc79671b`).

## Fix

- Every `Depends(get_db)` is now `Depends(get_db, scope="function")`: in the
  routers, the web routes and the auth dependency, which all share one
  session per request. Function scope ends the dependency after the path
  operation, which includes response serialization, and before the response
  is sent. So the commit happens first.
- `database.get_db`'s docstring says to always declare it this way.
- Tests: `tests/test_commit_before_response.py`, on REST v2 and v3. Every
  commit is slowed by 0.2 s so the race is deterministic. A separate SQLite
  connection then checks, at `http.response.start` of the PUT, that the
  label is committed. It fails on the old scoping (the label is missing at
  response start) and passes now.
