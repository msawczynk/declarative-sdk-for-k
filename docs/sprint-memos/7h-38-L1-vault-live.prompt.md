## Sprint 7h-38 L1 — Vault smoke live-proof transcript (codex live-mode)

You are a codex CLI live-mode worker. You are running inside a git worktree at `/Users/martin/Downloads/Cursor tests/dsk-wt-vault-live`, branch `cursor/smoke-vault-live-l1`, branched from `main` HEAD `91119c4` (after Sprint 7h-37 merge).

# Goal

Capture the first **sanitized live-proof transcript** for `keeper-vault.v1` by running the new `vaultOneLogin` smoke scenario against the lab tenant (`msawczyn+lab@acme-demo.com`, `keepersecurity.com`). Then bump `keeper-vault.v1.schema.json`'s `x-keeper-live-proof.status` from `experimental` to `supported`, citing the captured transcript path. Commit + push. NO PR — parent merges.

# Hardening contract (from `codex_live.sh`)

- NEVER echo secrets / env / config / TOTP / passwords / tokens / records.
- Prefer the committed harness `scripts/smoke/smoke.py` over ad-hoc `keeper` edits.
- Sanitise failure evidence (UID prefixes only, no full user records).
- Final reply: one DONE line `LIVE-OK <evidence>` or `LIVE-FAIL <reason>`.

# Live invocation

The harness already supports vault scenarios after Sprint 7h-37 merge. Authentication via env helper:

```
python3 scripts/smoke/smoke.py --scenario vaultOneLogin --login-helper env
```

Env vars `KEEPER_EMAIL`, `KEEPER_PASSWORD`, `KEEPER_TOTP_SECRET` are present (sourced by `codex_live.sh` from KSM record before launch).

# Required reading

1. `scripts/smoke/README.md` — auth, prerequisites.
2. `docs/live-proof/README.md` — sanitization rules, transcript file shape, where to put the file.
3. `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` — locate `x-keeper-live-proof` block.
4. `scripts/smoke/scenarios.py` — confirm `vaultOneLogin` is registered in vault registry.

# Workflow

1. Run a teardown first to clear any residue from earlier offline test runs:
   ```
   python3 scripts/smoke/smoke.py --scenario vaultOneLogin --login-helper env --teardown 2>&1 | tee /tmp/smoke-vault-teardown.log
   ```
   - Exit 0 (clean) or 4 (no residue to clean) is acceptable. Other exits → `LIVE-FAIL teardown rc=<n>`.
2. Run the full smoke cycle:
   ```
   python3 scripts/smoke/smoke.py --scenario vaultOneLogin --login-helper env 2>&1 | tee /tmp/smoke-vault-l1.log
   ```
   Expect exit 0. Final log line `SMOKE PASSED: create->verify->destroy cycle clean`.
3. If exit != 0 → `LIVE-FAIL smoke rc=<n>`. Capture last 50 lines of log to a sanitized post-mortem; do not commit raw log.
4. On success, build the sanitized transcript per `docs/live-proof/README.md`:
   - File: `docs/live-proof/keeper-vault.v1.<commander-pin>.sanitized.json` where `<commander-pin>` = `91119c4` (the main HEAD this slice branched from). If a different pin convention is used in `pam-environment.v1.<pin>.sanitized.json`, follow that convention exactly — read an existing file as template.
   - Body: JSON with the fields prescribed by `docs/live-proof/README.md`, including:
     - `family`: `keeper-vault.v1`
     - `scenario`: `vaultOneLogin`
     - `commander_pin` / `since_pin`
     - `tenant_fqdn`: `keepersecurity.com`
     - `tenant_account_redacted`: `msawczyn+lab@acme-demo.com` (per the existing live-proof corpus convention)
     - `phase_results`: array of phase entries (`validate ok`, `plan creates ok`, `apply ok`, `discover OK`, `verify OK`, `re-plan clean`, `destroy plan deletes ok`, `destroy apply ok`, `re-discover empty ok`)
     - `record_uid_prefixes`: list of 8-char UID prefixes only (NEVER full UIDs)
     - `marker_manager`: `keeper-pam-declarative` (verbatim, sanity check that it didn't accidentally mutate)
     - `notes`: short caveman bullets
   - Run `python3 -m json.tool` over the file to ensure strict-JSON validity (per LESSON `[worker][format-on-rebase-jsonc-trap]`).
   - Run `grep -E '[A-Za-z0-9_-]{22,}' docs/live-proof/keeper-vault.v1.*.sanitized.json` and inspect: every match must be either a 22-char base64 UID **prefix only** (e.g. `abcdefgh-truncated`) or a known constant. NO full UIDs. If a match looks suspicious, redact further.
5. Edit `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` `x-keeper-live-proof` block:
   - `status`: `experimental` → `supported`
   - `evidence`: include the new transcript path
   - `since_pin`: bump to `91119c4` (or current `main` HEAD; verify with `git rev-parse HEAD` — should match the worktree's branch base).
   - `notes`: extend to mention `vaultOneLogin` smoke matrix passed live this sprint.
6. Run `python3 -m pytest tests/ -q --no-cov` — must stay green (532+1).
7. Run `python3 -m json.tool` over both touched JSON files.
8. `git add -A && git commit -m "feat(keeper-vault.v1): live-proof transcript + status=supported (vaultOneLogin)"`.
9. `git push -u origin cursor/smoke-vault-live-l1`.
10. Output one final line: `LIVE-OK docs/live-proof/keeper-vault.v1.91119c4.sanitized.json` or `LIVE-FAIL <reason>`.

# Constraints

- Caveman-ultra in commit message body.
- Never echo secrets / TOTP / passwords / record bodies / record UIDs longer than 8 chars.
- Marker manager `MANAGER_NAME = "keeper-pam-declarative"` is UNTOUCHED at `keeper_sdk/core/metadata.py:27`.
- If smoke fails for a non-tenant reason (e.g., transient Commander glitch), retry ONCE before declaring `LIVE-FAIL`.
- If smoke fails because of a real bug in the vault scenario glue (Sprint 7h-37 merge weave), attempt a minimal fix in `scripts/smoke/smoke.py` and re-run. Document the fix in the commit body. If fix doesn't land in 1 attempt → `LIVE-FAIL <reason>` and revert any partial fix.
- Live invocation must use the `default` profile (today's tenant). Multi-profile is L2's slice, not this one.
