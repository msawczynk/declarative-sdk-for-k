# Changelog

All notable changes to `declarative-sdk-for-k` (`dsk`) land here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `pamUserNested` smoke scenario — proves nested `resources[].users[]`
  through schema, typed model, planner, and Commander normalization
  without claiming standalone top-level `pamUser` live support.
- Offline `pam rotation edit` argv mapping helper and stricter preview
  detection for rotation keys. Rotation remains preview/unsupported
  until live apply is proven.
- Offline post-import tuning argv helper for a safe subset of
  `pam connection edit` and `pam rbi edit` fields. Not wired into live
  apply yet.
- Bounded in-process Commander session refresh for `session_token_expired`
  during `pam project import` / `extend` and ownership-marker writes.
  This is unit-tested with synthetic exceptions; live proof is still
  pending.
- `examples/`: minimal `pamMachine` / `pamDatabase` / `pamDirectory` /
  `pamRemoteBrowser` manifests; CI validates + mock-plans every file.
- `SCAFFOLD.md`: LLM-readable repo map + design-vs-shipped reconcile.
- `ci(examples)`: new examples job + added to build needs.
- `scripts/smoke/scenarios.py` — registered live-smoke matrix
  (`pamMachine`, `pamDatabase`, `pamDirectory`, `pamRemoteBrowser`).
  `smoke.py` now accepts `--scenario NAME`; the identity / sandbox /
  destroy flow is invariant across scenarios. Unit tests in
  `tests/test_smoke_scenarios.py` validate each scenario against the
  offline schema + typed-model + planner stack so drift is caught
  without a tenant round-trip.
- `Provider.check_tenant_bindings(manifest) -> list[str]` protocol
  method. `validate --online` stage 5 now calls it and exits
  `EXIT_CAPABILITY` (`5`) on any returned issue. Commander
  implementation verifies pam_configuration titles resolve, each
  config has a `shared_folder_uid`, `gateway_uid_ref` pairings match
  the tenant, and declared `ksm_application_name` matches what the
  tenant actually bound. MockProvider returns `[]`. See
  `docs/VALIDATION_STAGES.md` for the per-stage exit-code contract.
- `docs/VALIDATION_STAGES.md` — complete stage-by-stage exit code
  contract, remediation pointers, passing / failing examples.
  Linked from `AGENTS.md`.
- `scripts/sync_upstream.py` — extracts the Keeper Commander capability
  surface (registered PAM group commands, argparse flags for
  `pam project import` / `extend` / `pam rbi edit` /
  `pam connection edit`, `ALLOW_PAM_*` enforcements, record-type field
  sets from `pam_import/README.md`) into
  `docs/CAPABILITY_MATRIX.md` + `docs/capability-snapshot.json`. Runs
  in `--check` mode for CI drift detection.
- `docs/CAPABILITY_MATRIX.md` + `docs/capability-snapshot.json` —
  pinned upstream surface for Commander `231f557c`.
- `.commander-pin` — single-line Commander SHA that CI clones and
  diffs against (`drift-check` job in `.github/workflows/ci.yml`).
- Schema hardening (`pam-environment.v1.schema.json`): typed fields
  for RDP options (`security`, `disable_authentication`,
  `load_balance_info`, `preconnection_id`, `preconnection_blob`,
  `disable_audio`, `disable_dynamic_resizing`, `enable_full_window_drag`,
  `enable_wallpaper`), audio (`audio_channels`, `audio_bps`,
  `audio_sample_rate`), and `text_session_recording` on
  `pam_remote_browser.options`. Non-breaking.
- `docs/COMMANDER.md`: new "Automated capability mirror" section
  linking to the pinned matrix and the DOR drift policy.
- `scripts/smoke/smoke.py --login-helper env` — live-smoke mode that
  exercises the public `EnvLoginHelper` fallback instead of the lab's
  `deploy_watcher.py` helper. `tests/test_smoke_args.py` pins the CLI
  switch.
- `tests/test_auth_helper.py` — unit coverage for env-var credential
  loading, Commander config warm-up, step-based `LoginUi` construction,
  and invalid config errors.
- `tests/test_renderer_snapshots.py` + `tests/fixtures/renderer_snapshots/`
  — snapshot coverage for Rich plan/diff/outcome layouts.
- `tests/test_dor_scenarios.py` — offline mapping for DOR `TEST_PLAN`
  cases, with v1.1-only gaps marked `xfail`.

### Changed
- Sibling `keeper-pam-declarative` repo reframed as a capability
  mirror (not a forward-looking Design of Record). Retired 10 design
  docs, rewrote README + SCHEMA_CONTRACT + PLATFORM_REFERENCE, added
  DRIFT_POLICY. The authoritative capability matrix now lives in this
  repo under `docs/` and is auto-generated.

- Initial public release scaffolding: `LICENSE` (MIT), `SECURITY.md`, `CHANGELOG.md`.
- GitHub Actions CI: ruff + mypy + pytest on Python 3.11 / 3.12 / 3.13.
- `AGENTS.md` — agent- and LLM-oriented operating manual (exit-code map,
  machine-readable command table, JSON contracts).
- `keeper_sdk.auth` reference login helper (`EnvLoginHelper`) so
  `KEEPER_SDK_LOGIN_HELPER` is now optional for the common case.
- `EnvLoginHelper` now implements Commander's full step-based
  `LoginUi`, loads `KEEPER_CONFIG` through Commander's config loader
  before env credentials are applied, and reuses persistent-login state
  without letting stale config credentials override env credentials.
- `docs/LOGIN.md` — helper contract + 30-line skeleton for custom flows.
- `V1_GA_CHECKLIST.md` — roadmap toward v1.0.0; now tracks full-K
  scope (vault records, shared folders, teams, roles, enterprise
  config, KSM apps, PAM, compliance, rotation, migration) rather
  than PAM-only.
- `tests/test_perf.py` now asserts peak RSS under the 500-resource
  lifecycle smoke to catch memory regressions.
- Packaging metadata now uses the SPDX `license = "MIT"` form and drops
  the deprecated license classifier.
- Retained `DeleteUnsupportedError` as a public compat shim subclassing
  `CapabilityError`; provider failures now use `CapabilityError` directly.
- Added `pyotp` as an unpinned runtime dependency because the built-in
  `EnvLoginHelper` imports it lazily during Commander login.

### Changed
- **Project renamed** across two hops:
  - `keeper-declarative-sdk` → `pamform` (PAM-scoped rebrand).
  - `pamform` → `declarative-sdk-for-k` (scope broadened to the
    full K surface; primary CLI is now `dsk`). `pamform` and
    `keeper-sdk` remain as CLI aliases through 1.x.
- Import path stays `keeper_sdk` in 1.x (keeps the 106-test suite
  green). Will rename to `declarative_sdk_k` in 2.0 with a shim.
- `pyproject.toml`: pin `keepercommander>=17.2.13,<18`; require
  Python `>=3.11`; expanded `keywords` + `classifiers`; homepage
  points at `msawczynk/declarative-sdk-for-k`.
- Env-var convention rename: `PAMFORM_CI` → `DSK_CI`,
  `PAMFORM_PREVIEW` → `DSK_PREVIEW`.

## [0.y.z] — pre-release history

Recorded in `AUDIT.md` and `git log` on the `main` branch. Notable landmarks:

- **2026-04-24 (late)** — C1/C2/C3 + H1..H6 closure; capability gaps
  surface as plan-time CONFLICT rows so `plan == apply --dry-run == apply`.
  106/106 tests green.
- **2026-04-24 (early)** — "finish-it-all" pass D-1..D-7 against
  Commander release branch 17.2.13+40. JSON migration for `pam gateway
  list` / `pam config list`. Live-smoke GREEN end-to-end.
- **2026-04-24 (review)** — devil's-advocate sweep, 82 → 95 tests.
- **pre-2026-04-24** — W1..W20 sdk-completion milestones (see
  `AUDIT.md`).
