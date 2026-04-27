## Sprint 7h-37 S4 — GH Actions parallel matrix design memo (codex readonly)

You are a codex CLI **readonly** worker. Produce a concrete design memo for a GH Actions nightly matrix that runs `scripts/smoke/smoke.py` across 3 profiles × 6 PAM scenarios in parallel against the lab tenant. NO code changes; this memo drives Sprint 7h-38 L4.

# Required reading

1. `.github/workflows/ci.yml` — current job matrix, secrets surface.
2. `scripts/smoke/README.md` — current `--login-helper env` flow with KEEPER_EMAIL/KEEPER_PASSWORD/KEEPER_TOTP_SECRET.
3. `docs/live-proof/README.md` — concurrency rule.
4. `pyproject.toml` — Python version + deps.
5. CDX-1 memo `/tmp/dsk-cdx-1-multiprofile.md` (per-profile axes table).
6. CDX-2 memo `/tmp/dsk-cdx-2-concurrency.md` (Commander config copy semantics).

# Deliverable shape (~100-140 lines)

```
# GH Actions parallel smoke matrix — design memo (CDX-S4, <UTC ISO>)

## Trigger
- Nightly cron `0 4 * * *` UTC.
- Manual `workflow_dispatch` for ad-hoc runs.

## Job structure
- One job: `smoke-matrix` (in addition to existing `build` job; depends on it).
- Matrix dimensions:
  - `profile`: [p1, p2, p3]
  - `scenario`: [pamMachine, pamDatabase, pamDirectory, pamRemoteBrowser, pamUserNested]  (pamUserNestedRotation excluded — preview-gated)
- `fail-fast: false` so one failure doesn't kill the rest.
- Concurrency group: `smoke-matrix-${{ github.workflow }}` with `cancel-in-progress: true` to prevent overlapping cron runs.

## Per-job steps
1. Checkout (full).
2. Set up Python 3.11.
3. Install: `pip install -e ".[dev]" keepercommander pyotp keeper_secrets_manager_core`.
4. Materialise per-profile JSON file from secrets:
   - Each profile reads `secrets.SDK_SMOKE_PROFILE_<UPPER>_JSON`. (Operator provisions these as a JSON blob each.)
   - Write to `scripts/smoke/profiles/<profile>.json`.
   - Materialise per-profile Commander config from `secrets.SDK_SMOKE_COMMANDER_CONFIG_<UPPER>` to the path declared in the profile JSON.
5. Materialise admin KSM config once: `secrets.SDK_SMOKE_KSM_CONFIG`.
6. Provision testuser identity: `python3 scripts/smoke/identity.py --profile <profile>`.
7. Run smoke: `python3 scripts/smoke/smoke.py --profile <profile> --scenario <scenario> --login-helper env --parallel-profile`.
8. Upload artifact: smoke log + sanitized post-mortem JSON, retention 14 days.
9. On failure: emit grouped log section + last 200 lines of smoke output.

## Required secrets (operator provisions ONCE)
- `SDK_SMOKE_KSM_CONFIG`: full ksm-config.json blob.
- `SDK_SMOKE_PROFILE_P1_JSON`, `..._P2_JSON`, `..._P3_JSON`: per-profile config blob.
- `SDK_SMOKE_COMMANDER_CONFIG_P1`, `..._P2`, `..._P3`: per-profile admin commander-config.json blob (each pointing at the same admin user but with isolated cache DB paths).
- (Already exists for any current secret-needing job — confirm names by reading `ci.yml`.)

## Cost estimate
- 3 × 5 = 15 jobs/night.
- ~3min per job (per current `scripts/smoke/README.md` smoke run time estimates).
- Total: ~45min compute/night. Free for public repo on GH Actions.

## Concurrency safety
- All 15 jobs run on different runners — no cross-job process collision.
- Within tenant: profile lock files prevent two jobs from grabbing the same profile simultaneously (S3 deliverable). Matrix `fail-fast: false` + `cancel-in-progress: true` on the workflow keeps the lock window bounded.

## Reporting
- After matrix completes, a summary job aggregates results into a single GitHub Actions Job Summary (Markdown table).
- Optional: post a comment to a tracking issue (`#1` or new "nightly smoke" issue).

## Risk + rollback
- Risk 1: tenant rate limit. Mitigation: cap matrix concurrency to 5 (`max-parallel: 5`) so only 5 of the 15 cells run at once. Operator can raise after first stable week.
- Risk 2: profile lock collision if two scenarios land on same profile in the same run (impossible with current matrix shape, but defended by lock file).
- Risk 3: secrets accidentally logged. Mitigation: `actions/setup-python@v5` masking + `set-output` only on sanitized values; smoke log already redacts via `secret_leak_check`.
- Rollback: delete the workflow file; matrix is additive and does not change existing CI.

## Live-proof artifact capture
- Each successful nightly auto-commits a sanitized transcript artifact to `docs/live-proof/auto/<date>-<profile>-<scenario>.sanitized.json` IF status changed (e.g. flake → green or vice versa). This is OUT OF SCOPE for the first matrix landing — file as Sprint 7h-39+ follow-up.

## CANDIDATE LESSON
- 2026-04-27 [ci][parallel-smoke-matrix] <one line>
```

# Constraints

- Read-only.
- Cite `file:line` for every claim.
- Output the full memo as your final response.
