# `ORDER BY key` sorts issue keys as strings

## Status: Fixed

## Summary

JQL `ORDER BY key` (and `issuekey`), and the default search order, sorted on
the `issues.key` string, so `RHAISTRAT-10` came before `RHAISTRAT-2`. Jira
sorts keys by project, then by issue number as an integer.

## Impact

strat-creator slices batches by searching `... ORDER BY key ASC` and paging
with `nextPageToken`. With string order, batches formed in a different order
than they do in production. Any batch past nine issues was affected.

Found by the Breadboard `rhaistrat-initiative-tests` preflight
(`search_paging_and_order`, `markov-run-eb923d73`).

## Fix

- `jql/transformer.py` maps `key` and `issuekey` to two sort expressions: the
  project prefix, then the number after the first `-`, cast to an integer.
  Project keys never contain `-`. `search_service.py` uses the same
  expressions for the default order.
- Tests: `tests/test_search.py`. These cover ASC and DESC on REST v2
  `/search` and v3 `/search/jql`, the default GET order, and grouping by
  project. Five of the six fail without the fix.
