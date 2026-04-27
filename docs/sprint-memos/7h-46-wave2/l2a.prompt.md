# Wave2 L2a — keeper-vault.v1 second live scenario

You are a codex **live** worker. Lab tenant grant in scope.

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-l2a-vault-scenario2`, branch `cursor/l2a-vault-scenario2`, base 535e03f.

Goal: SECOND live `keeper-vault.v1` round-trip (different scenario from existing 91119c4 transcript) — exercises `databaseCredentials` or `serverCredentials` record types + multi-record manifest. Sanitized transcript appended to `keeper-vault.v1.schema.json` `x-keeper-live-proof.evidence[]`.

# Required reading
1. `docs/live-proof/keeper-vault.v1.91119c4.sanitized.json` (existing transcript — your scenario MUST be DIFFERENT, e.g. multi-record vs single-record, or different record_type).
2. `docs/live-proof/keeper-vault.v1.sanitized.template.json` (canonical shape).
3. `examples/sample.vault.yaml` or any new examples added in W4 (`vault-records.yaml`, `vault-record-types.yaml`).
4. `keeper_sdk/core/vault_models.py` for record type definitions.
5. `keeper_sdk/cli/main.py` validate/plan/apply for vault family.
6. `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` (find `x-keeper-live-proof.evidence[]`).
7. LESSON `[orchestration][live-write-bg-via-nohup]` 7h-38.

# Hard requirements
1. Pick scenario name: `vaultMultiRecordCrud` (3 records: login + databaseCredentials + serverCredentials, full CRUD round-trip).
2. Build manifest in worktree (e.g. `/tmp/vault-l2a-manifest-<TS>.yaml`).
3. Live: `dsk validate <manifest>` → `dsk plan <manifest>` → `dsk apply <manifest>` → re-discover → re-diff = 0 changes.
4. Restore: optionally delete created records via second apply with `allow_delete=true`.
5. Capture raw output → sanitize → save `docs/live-proof/keeper-vault.v1.<short-sha>.multirecord.sanitized.json`.
6. Append new path to `keeper-vault.v1.schema.json` `x-keeper-live-proof.evidence[]`. DO NOT replace.
7. Add 1 offline test in `tests/test_keeper_vault_schema.py` (NEW or extend).
8. ruff + mypy + full suite green.
9. `git add -A && git commit -m "feat(vault): L2a vaultMultiRecordCrud live-proof transcript (Wave2)"`.
10. `git push -u origin cursor/l2a-vault-scenario2`.
11. Output `DONE: cursor/l2a-vault-scenario2 <sha>` or `LIVE-FAIL: <one-line>` or `BLOCKED: <one-line>`.

# Sanitization (CRITICAL)
- See L1a prompt sanitization section.
- Vault values especially sensitive — use `secret_leak_check` rigorously.

# Constraints
- ONLY touches: `docs/live-proof/keeper-vault.v1.<sha>.multirecord.sanitized.json` (NEW), `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` (evidence[] append), `tests/test_keeper_vault_schema.py` (NEW or extend).
- Disjoint from L1a (pam), V9a (sharing), M-series.
