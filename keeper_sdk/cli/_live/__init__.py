"""Live-test infrastructure.

Internal package. Public entry point is the `dsk live-smoke` CLI verb
(see `keeper_sdk/cli/main.py`). Modules:

- `transcript`: sanitized proof-transcript writer. Strips secrets/UIDs
  before writing to disk, then writes the sanitized transcript to the
  path referenced by a schema's `x-keeper-live-proof.evidence` field.
- `runbook`: the smoke-loop logic — bootstrap → login → apply → diff →
  cleanup. Each phase gates on the prior phase's success.

Per docs/LIVE_TEST_RUNBOOK.md, the parent owns credentials and runs
this; the SDK owns the loop + the sanitization.
"""
