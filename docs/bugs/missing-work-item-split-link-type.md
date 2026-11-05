# Missing `Work item split` link type

## Status: Fixed

## Summary

Red Hat Jira links split RFEs to their parent with the `Work item split`
link type. rfe-creator's `split_submit.py` reads that name from its type
descriptor (`identity.jira.split_link_type`). The emulator seeded only
`Issue split`, so split submission failed to create its links.
rfe-creator's own test suite worked around this by patching
`seed_service.LINK_TYPES`.

## Fix

- Seeded `Work item split` (inward `is split from`, outward `split to`).
- Tests: `tests/test_links.py::test_work_item_split_link_type`, on REST v2
  and v3.
