# Wave2 V9a — sharing folder lifecycle live transcript

You are a codex **live** worker. Lab tenant grant in scope.

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-v9a-sharing-folder-lifecycle`, branch `cursor/v9a-sharing-folder-lifecycle`, base 535e03f.

Goal: FIRST live `keeper-vault-sharing.v1` round-trip — folder lifecycle (user_folder + shared_folder creation, ACL grant, re-discover round-trip clean). NO schema flip yet (deferred to Wave3 V9-flip after V9b record-share transcript also lands).

# Required reading
1. `examples/sharing.example.yaml` (V7c minimal sharing manifest).
2. `keeper_sdk/core/sharing_models.py` (V5a Pydantic models).
3. `keeper_sdk/core/sharing_diff.py` (V5a/V6b folder + shared_folder diff logic).
4. `keeper_sdk/providers/commander_cli.py` 11 sharing methods (V7b, lines ~2000-2400, currently stubbed against `_run_cmd` — verify if real Commander CLI subcommands exist or need replacement during live run).
5. `scripts/smoke/scenarios.py` `VAULT_SHARING_LIFECYCLE` SPEC (V8a Wave1).
6. `scripts/smoke/smoke.py` family-dispatch for `keeper-vault-sharing.v1` (V8b Wave1).
7. `docs/live-proof/keeper-vault.v1.sanitized.template.json` (canonical events[] shape).
8. LESSON `[smoke][in-run-self-fix-during-live-proof]` 7h-38 — V7b's stubbed sharing methods may not match real Commander CLI argv exactly; expect to self-fix.
9. LESSON `[orchestration][live-write-bg-via-nohup]` 7h-38.

# Hard requirements
1. Build minimal sharing manifest at `/tmp/sharing-v9a-manifest-<TS>.yaml`: 1 user_folder + 1 shared_folder + 1 record + 1 share_folder ACL grant (default share to a specific user). Use lab tenant test users (`KEEPER_LAB_TEST_USER_EMAIL` env or hardcoded list from `~/.keeper/commander-config.json`).
2. Live: `dsk validate` → `dsk plan` → `dsk apply` → re-discover → re-diff.
3. **EXPECTED**: V7b stubbed methods may fail on real Commander argv. SELF-FIX: read raw error, patch the offending method in `keeper_sdk/providers/commander_cli.py`, add offline test for the corrected argv shape, retry live. Cite each fix in transcript `notes`.
4. Restore: second apply with `allow_delete=true` cleaning up created folders.
5. Capture raw → sanitize → save `docs/live-proof/keeper-vault-sharing.v1.<short-sha>.folderlifecycle.sanitized.json`.
6. **DO NOT** flip schema status `scaffold-only` → `supported` — this is the FIRST of 2 transcripts; flip happens in Wave3 V9-flip.
7. **DO** update `keeper-vault-sharing.v1.schema.json` `x-keeper-live-proof.evidence[]` array (add new path; if array is `"pending"` string, replace with array of 1 entry).
8. **DO** update `x-keeper-live-proof.notes` to cite "V9a folder lifecycle landed; awaiting V9b record share lifecycle for status flip".
9. Add 1-2 offline tests in `tests/test_keeper_vault_sharing_schema.py` (NEW or extend) pinning the evidence array.
10. ruff + mypy + full suite green.
11. `git add -A && git commit -m "feat(sharing): V9a folder-lifecycle live-proof transcript (Wave2)"`.
12. `git push -u origin cursor/v9a-sharing-folder-lifecycle`.
13. Output `DONE: cursor/v9a-sharing-folder-lifecycle <sha>` or `LIVE-FAIL: <one-line>` or `BLOCKED: <one-line>`.

# Sanitization (CRITICAL)
- See L1a prompt sanitization section. Sharing transcripts may contain ACL grantee email addresses — hash those too (last 8 sha256 over email).

# Constraints
- ONLY touches: `docs/live-proof/keeper-vault-sharing.v1.<sha>.folderlifecycle.sanitized.json` (NEW), `keeper_sdk/core/schemas/keeper-vault-sharing/keeper-vault-sharing.v1.schema.json` (evidence[] update + notes; NO status flip), `tests/test_keeper_vault_sharing_schema.py` (NEW or extend), `keeper_sdk/providers/commander_cli.py` (only if self-fix needed for stubbed sharing argv).
- Disjoint from L1a, L2a, M-series.
- If `commander_cli.py` self-fix needed, ALSO update offline tests in `tests/test_commander_cli_sharing.py` (V7b's tests) to cover the corrected argv. This bleeds into V7b's territory but is necessary for live validation.
