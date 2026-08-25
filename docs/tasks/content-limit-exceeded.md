# Implement Jira description content-limit behavior

Status: pending

## Problem

The emulator currently accepts arbitrarily large issue descriptions. Jira
rejects descriptions that exceed its content limit with HTTP 400 and the
following field error:

```json
{"errorMessages": [], "errors": {"description": "CONTENT_LIMIT_EXCEEDED"}}
```

This mismatch prevents clients such as `strat-creator` from exercising their
real attachment fallback path in the emulator. In production, an oversized
description can trigger a fallback to an append-only strategy attachment;
today the emulator accepts the oversized update instead.

Related evidence and consumers:

- `RHAIFIRST-542` — append-only Jira attachment behavior.
- `RHAISTRAT-1545` — production issue that exposed the missing emulator
  behavior.
- `RHAIRFE-1622` — source RFE whose content contributed to the oversized
  description.

## Requirements

1. Add a configurable description-size limit to the emulator. The default
   must be `32767` logical description characters, matching Jira's documented
   default text-field limit. Tests must be able to override it with a small
   deterministic value.
2. Measure the description's logical text content after ADF normalization,
   using the same character unit as Jira's text-field limit. Do not measure
   the raw serialized ADF JSON size or use the local Markdown length as a
   substitute. Document the unit, default threshold, and override in the
   emulator configuration or API documentation.
3. Enforce the limit before mutating the issue or recording history. A
   rejected create or update must leave the issue unchanged.
4. Return Jira-compatible HTTP 400 responses with the exact `description` /
   `CONTENT_LIMIT_EXCEEDED` field error for both REST API v2 and v3 issue
   writes.
5. Ensure all other supported write surfaces that can set an issue
   description, including MCP-backed operations where applicable, share the
   same validation rule rather than silently accepting a larger payload.
6. Preserve existing behavior for descriptions at or below the configured
   limit, including ADF round-tripping and changelog behavior.

## Tests and integration coverage

- Add boundary tests for below-limit, exactly-at-limit, and above-limit ADF
  descriptions.
- Test REST v2 and v3 create/update responses and verify rejected writes do
  not change the stored description or history.
- Test the MCP description-write path if it exposes one.
- Add a strat-creator integration case that configures a small emulator limit,
  triggers `CONTENT_LIMIT_EXCEEDED`, and verifies the client reaches the
  attachment fallback and publishes its marker only after a successful upload.
- Keep the scenario deterministic and non-LLM; use generated ADF fixtures.

## Definition of done

- The emulator reproduces the production error shape and mutation semantics.
- REST v2, REST v3, and applicable MCP tests pass.
- The strat-creator overflow-to-attachment integration test passes against the
  emulator.
- The configured default and test override are documented.
