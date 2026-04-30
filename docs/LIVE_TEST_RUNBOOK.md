# LIVE_TEST_RUNBOOK

**Who may run live (Keeper / Commander on a tenant):**

- **Any** maintainer, human, or **LLM agent** (Composer, subagent, Codex, etc.) **may**
  run live against the lab tenant when this runbook is followed and the host has
  a valid KSM/Commander credential path (see `ksm_login_preflight`, profile/env). It
  is **not** limited to a “primary” or “parent” session — the discriminant is
  **whether creds and policy are in effect**, not agent *kind*.
- The lab tenant is a **developer sandbox**; use the committed harnesses only
  (`scripts/smoke/smoke.py`, `pytest tests/live/…` with `KEEPER_LIVE_TENANT=1` per
  this runbook). Matches [`AGENTS.md`](../AGENTS.md) **Autonomous execution**.
- **Not** a blanket “agents have no access”: the gap is **no credential path**, not
  “not primary.”
- **Sessions that do not** receive KSM/Commander (typical: CI, default Codex
  offline sandbox, Task without env) **MUST NOT** be pointed at ad hoc `keeper` /
  tenant mutation. If a **worker** is to run live, the operator must pass the same
  env and network as a human (e.g. `codex_live` / explicit cred injection) — still
  via the **committed** harness, not ad hoc.

## Why this exists

Per `docs/V2_DECISIONS.md` Q4, every schema family has an
`x-keeper-live-proof.status` that can only graduate from
`preview-gated` to `supported` when a sanitized live-tenant transcript
is wired in. Live tests are the only telling tests — unit tests prove
shape, live tests prove the *behavior* against a real Commander +
Keeper Vault.

**See also:** [`scripts/daybook/README.md`](../scripts/daybook/README.md) — forwarder
to session boot / append / sync for **continuity** only; it does **not** replace
this runbook or [`scripts/smoke/README.md`](../scripts/smoke/README.md).

## Pre-flight (run before every live session)

1. Confirm tenant (`admin@example.com` for the lab).
2. `bash ~/.cursor-daybook-sync/scripts/ksm_login_preflight.sh` —
   verifies a usable KSM session before spending tenant API quota.
3. `git status` clean on the repo. Live tests write artefacts under
   `.live-smoke/` (gitignored).
4. Confirm `.commander-pin` matches `keepercommander` installed
   version: `pip show keepercommander | rg Version`.

### KSM Profile Setup (one-time)

Required for `--login-helper profile` smoke runs:

1. **Smoke profile** — create `~/.config/dsk/profiles/default.json` based on `scripts/smoke/profiles/default.example.json`. Set:
   - `default_admin_record_uid`: lab admin KSM record UID (ask maintainer)
   - `ksm_config`: path to lab `ksm-config.json` (e.g. `~/.keeper/ksm-config.json`)
   - `admin_email`: lab admin email
   - `pam_config_title`: title of the `sdk-smoke-pam-config` PAM configuration in the tenant

2. **KSM config** — `ksm-config.json` must be in the location specified by `ksm_config` above. The lab config is available from the lab KSM app (see `AGENTS.md` workspace rule for record UIDs).

3. **Target user** — `ensure_sdktest_identity()` uses the "reuse path": if the admin vault contains a login record for the target email with all fields (login, password, oneTimeCode), no `DSK_SMOKE_TARGET_PASSWORD` env var is needed.

4. **PAM configuration fixture** — `sdk-smoke-pam-config` must exist in the tenant (created once via `keeper pam config new --title sdk-smoke-pam-config`).

## Run a single live test (recommended for first proof)

```bash
export KEEPER_LIVE_TENANT=1
export KEEPER_LIVE_KSM_RECORD_UID=<uid-of-bootstrap-record>
export KEEPER_LIVE_KSM_CONFIG=$HOME/.keeper/ksm-config.json   # recommended headless path
# Or, for local Commander-session mode, leave KEEPER_LIVE_KSM_CONFIG unset and use:
# export KEEPER_CONFIG=$HOME/.keeper/config.json

python3 -m pytest tests/live/test_ksm_bootstrap_smoke.py -v
```

Without `KEEPER_LIVE_TENANT=1` the test is skipped at collection
time (see `tests/live/conftest.py`) — so plain `pytest tests/` stays
offline.

If the command exits 0 but reports:

```text
SKIPPED [1] tests/live/test_ksm_bootstrap_smoke.py:39: live-tenant test missing env vars: KEEPER_LIVE_KSM_RECORD_UID
```

then no live proof ran. Re-run only after the operator injects
`KEEPER_LIVE_KSM_RECORD_UID` for the bootstrap admin login record, plus
either `KEEPER_LIVE_KSM_CONFIG` for the headless KSM helper or a valid
Commander session config for local commander mode. Add `-rs` while
diagnosing skips so pytest prints the exact missing prerequisite.

## Run the full smoke loop (CLI verb)

```bash
dsk live-smoke \
  --ksm-record-uid <uid> \
  --manifest examples/smoke.yml \
  --workdir .live-smoke \
  --evidence-out evidence/pam-environment.v1.json \
  --schema-family pam-environment \
  --schema-version v1
```

The verb runs: bootstrap-ksm → login probe → apply → diff (must
re-plan clean) → cleanup. Each phase short-circuits the rest if it
fails; the transcript still records every phase (failed phases keep
their error, skipped phases get `status: "skipped"`).

## Sanitization & evidence

The transcript writer (`keeper_sdk.cli._live.transcript`):

- Strips dict values whose key is in `_SECRET_KEYS` (`password`,
  `token`, `private_key`, `config`, `appKey`, `applicationKey`,
  `totp`, …).
- Fingerprints anything that LOOKS like a Keeper UID (20–28 char
  URL-safe base64) into `<uid:sha256-8>`. Same UID always maps to
  the same fingerprint within a transcript so re-reads are auditable.
- After write, runs `secret_leak_check` against the final bytes; if
  the check fails the file is unlinked and the verb exits non-zero.

The CI workflow `.github/workflows/live-smoke.yml` repeats the leak
check via `grep` as a belt-and-braces guard. **If you see ANY
warning from either pass, do NOT commit the evidence file** — open
an issue with the warning text + a description of which phase
generated it, and treat it as a sanitizer regression.

## Wiring evidence into a schema family

Once a green transcript exists at e.g. `evidence/pam-environment.v1.json`:

1. Move it to a stable, repo-tracked path
   (`docs/live-proof/<family>.<version>.<commander-pin>.json`).
2. Update the family schema's `x-keeper-live-proof` block:

   ```json
   "x-keeper-live-proof": {
     "status": "supported",
     "evidence": "docs/live-proof/pam-environment.v1.89047920a0.json",
     "since_pin": "89047920a0",
     "notes": "live-smoke 2026-04-26: bootstrap+login+apply+diff clean"
   }
   ```

3. Bump `since_pin` only when re-proving against a newer Commander
   pin (i.e. after `sync_upstream` lands). Older pin's evidence stays
   in the same `docs/live-proof/` folder for audit.

## Failure recovery

If `apply` succeeds but `diff` doesn't re-plan clean:

- Capture the non-clean diff output (already in the transcript).
- This signals a planner / provider disagreement — open a worker
  task to bisect which `change.kind` is recurring.
- DO NOT mark the schema family `supported`. Re-run after fix.

If `bootstrap` fails before login: most common cause is a stale
KSM application record. Use Keeper Commander UI to delete the
existing application binding, regenerate, and retry.

## Cadence

- Run live-smoke for `pam-environment.v1` after every
  `.commander-pin` bump.
- Run live-smoke for any schema family whose `since_pin` is more
  than 2 pin-bumps stale.
- Run before tagging any `v1.x` release.
