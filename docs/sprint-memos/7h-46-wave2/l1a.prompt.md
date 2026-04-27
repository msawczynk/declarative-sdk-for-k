# Wave2 L1a — pamMachine live transcript

You are a codex **live** worker. Lab tenant grant in scope.

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-l1a-pam-machine`, branch `cursor/l1a-pam-machine`, base 535e03f.

Goal: live PAM `pamMachine` round-trip (validate → plan → apply → re-discover → re-diff = 0). Sanitized transcript. Append evidence to `keeper-pam-environment.v1.schema.json` `x-keeper-live-proof.evidence[]` (DO NOT replace; this is family already `supported`).

# Required reading
1. `examples/pam-machine.yaml` (existing scenario yaml).
2. `keeper_sdk/cli/main.py` validate/plan/apply commands.
3. `scripts/smoke/smoke.py` `--scenario pamMachine --provider commander_cli` flow.
4. `docs/live-proof/README.md` (sanitization, naming).
5. `docs/live-proof/keeper-vault.v1.91119c4.sanitized.json` (template shape).
6. `docs/live-proof/keeper-vault.v1.sanitized.template.json` (canonical events[] shape).
7. `keeper_sdk/core/schemas/keeper-pam-environment/keeper-pam-environment.v1.schema.json` (find `x-keeper-live-proof.evidence[]` array).
8. LESSON `[orchestration][live-write-bg-via-nohup]` 7h-38.
9. LESSON `[smoke][in-run-self-fix-during-live-proof]` 7h-38.

# Hard requirements
1. Source Commander auth: `~/.keeper/commander-config.json` or KEEPER_CONFIG path. Lab tenant `msawczyn+lab@acme-demo.com` only.
2. Run `python -m scripts.smoke.smoke --scenario pamMachine --provider commander_cli` (or equivalent live invocation).
3. Capture raw stdout/stderr to `/tmp/pam-machine-l1a-raw-<TS>.log`.
4. Sanitize → save `docs/live-proof/keeper-pam-environment.v1.<short-sha>.machine.sanitized.json`. Use `keeper_sdk.cli._live.transcript.secret_leak_check` (or `keeper_sdk.core.redact`).
5. Append the new file path to `keeper-pam-environment.v1.schema.json` `x-keeper-live-proof.evidence[]`. DO NOT replace existing entries. DO NOT change `status` (already `supported`).
6. Add 1 offline test in `tests/test_keeper_pam_environment_schema.py` (NEW or extend) pinning the new evidence array length + entry path.
7. Verify: ruff + mypy + full suite green.
8. `git add -A && git commit -m "feat(pam): L1a pamMachine live-proof transcript (Wave2)"`.
9. `git push -u origin cursor/l1a-pam-machine`.
10. Output `DONE: cursor/l1a-pam-machine <sha>` or `LIVE-FAIL: <one-line>` or `BLOCKED: <one-line>`.

# Sanitization (CRITICAL)
- NEVER commit raw stdout/stderr.
- NEVER leak secrets, passwords, TOTP, vault values.
- Tenant identifier: hash + last 8 chars of sha256(KEEPER_USER).
- If self-fix needed, capture in transcript `notes` field per 7h-38 LESSON.

# Constraints
- ONLY touches: `docs/live-proof/keeper-pam-environment.v1.<sha>.machine.sanitized.json` (NEW), `keeper_sdk/core/schemas/keeper-pam-environment/keeper-pam-environment.v1.schema.json` (evidence[] append), `tests/test_keeper_pam_environment_schema.py` (NEW or extend).
- Disjoint from L2a (vault), V9a (sharing), M-series.
