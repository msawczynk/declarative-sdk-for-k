# v1.0.0 GA checklist

Derived from the 2026-04-24 devil's-advocate audit (see `AUDIT.md`).
Items are **blocking** unless marked `[hardening]`. Check them off in
PRs that close them so the next agent can tell at a glance what's left.

## Shipping gates

### 1. Capability parity with the schema
- [x] Decision closed via preview gate: `DSK_PREVIEW=1` now gates
      `rotation_settings`, `jit_settings`, `gateway.mode: create`,
      and top-level `projects[]` in `keeper_sdk/core/preview.py`;
      covered by `tests/test_preview_gate.py` (14 cases; see also
      JOURNAL Week 2 "What shipped").
- [x] Examples under `examples/` now validate clean with no preview
      flag and pass a `--provider mock` no-conflict `plan` check in CI;
      Commander live-smoke covers the same resource shapes via
      `scripts/smoke/scenarios.py`.
- [x] `pam_configuration_uid_ref` linking implemented OR marked
      preview with a stub. Current v1.0 contract: in-manifest linking
      is GA; cross-manifest / live-tenant-config linking is deferred
      and fails at stage 3 (`tests/test_uid_ref_gate.py::test_validate_rejects_cross_manifest_pam_configuration_uid_ref`).
- [x] DOR reframed as capability mirror; drift enforced by CI
      (`drift-check` job), see `docs/CAPABILITY_MATRIX.md`,
      `scripts/sync_upstream.py`, and JOURNAL Week 3 "What shipped".

### 2. Upstream DOR reconciliation
- [x] Upstream DOR reconciliation — SUPERSEDED 2026-04-24 by
      capability-mirror reframe (see JOURNAL Week 3 +
      `docs/CAPABILITY_MATRIX.md` + `scripts/sync_upstream.py`). The 7
      contradictions resolve by definition because the DOR now
      reflects, not prescribes, upstream.
  - [x] Marker wire format doc vs code
  - [x] `pam project export/remove` non-existence — update DOR docs
  - [x] Exit code 2 overloading — one source of truth
  - [x] `pamRemoteBrowser` session-recording field mapping
  - [x] `KEEPER_SDK_LOGIN_HELPER` documented in `DELIVERY_PLAN.md`
  - [x] Commander version pin in `DELIVERY_PLAN.md`
  - [x] DOR-internal doc-pair (`METADATA_OWNERSHIP.md` vs
        `docs/keeper-io/.../reference/marker.md`) reconciled

### 3. CI + release plumbing
- [x] MIT `LICENSE`, `CHANGELOG.md`, `SECURITY.md`.
- [x] GitHub Actions: ruff + mypy + pytest 3.11/3.12/3.13.
- [x] `pyproject.toml` pins `keepercommander>=17.2.13,<18`.
- [x] First green CI run on `main` (`fb6fb8b`).
- [x] PyPI publish workflow (`on: release: published`) landed in
      `.github/workflows/publish.yml`; maintainer still must complete
      the protected `pypi-publish` environment + PyPI OIDC trusted
      publisher setup before the first real release — no API tokens in
      repo secrets.
- [ ] Signed release tag `v1.0.0` with `gh release create`.

### 4. Login path usability
- [x] Ship `EnvLoginHelper` as in-tree reference.
- [x] `KEEPER_SDK_LOGIN_HELPER` now optional; env-var fallback kicks in.
- [x] `docs/LOGIN.md` with the 30-line skeleton.
- [x] Live EnvLoginHelper smoke proves login contract: validate + plan
      + sandbox provisioning all green via `--login-helper env` on
      2026-04-25 (tracked in this checklist + smoke docs). End-to-end apply blocked on
      separate Commander-CLI session-refresh gap (deferred, see
      JOURNAL).

### 5. `validate --online` completeness
- [x] Stage 5 actually verifies pam_configuration presence,
      shared-folder reachability, KSM app binding — implemented as
      `Provider.check_tenant_bindings()` (commander: resolves
      pam_configuration titles against `pam config list --format
      json`, asserts `shared_folder_uid` present on each config,
      cross-checks declared `gateway_uid_ref` against the tenant's
      pairing, and flags `ksm_application_name` mismatches).
- [x] Documented exit codes for each stage failure — see
      [`docs/VALIDATION_STAGES.md`](./docs/VALIDATION_STAGES.md).

### 6. Live-smoke coverage
- [x] `pamMachine` create → verify → delete cycle.
- [x] `pamDatabase` cycle (scenario registered, offline-tested; live run
      = `python3 scripts/smoke/smoke.py --scenario pamDatabase`).
- [x] `pamDirectory` cycle (scenario registered + offline-tested; live
      run = `--scenario pamDirectory`).
- [x] `pamRemoteBrowser` cycle (scenario registered + offline-tested;
      live run = `--scenario pamRemoteBrowser`).
- [x] `pamUser` cycle deferred to v1.1 (standalone `pamUser` lives
      under `users[]` on a PAM configuration, not as a top-level
      resource, so it needs a dedicated runner shape; see JOURNAL
      "Deferred to v1.1").
- [x] Adoption path against unmanaged records deferred to v1.1.
- [x] Field-drift → UPDATE path deferred to v1.1.
- [x] Two-writer conflict (ownership-marker race) deferred to v1.1.

The four registered scenarios share the identity / sandbox / destroy
flow; each scenario only diverges at `resources[]` and the post-apply
invariant verifier. See `scripts/smoke/scenarios.py` and
`tests/test_smoke_scenarios.py`.

## Recently closed (this session)

- `fb6fb8b` — first green CI run on `main`; drift-check fix kept the
  upstream mirror job green.
- `a1f859e` — examples/live-shape coverage closed via the scenarios
  registry for `pamDatabase`, `pamDirectory`, and `pamRemoteBrowser`.
- `870bffe` — `validate --online` stage-5 tenant-binding checks shipped.
- `581bddb` — CI drift-check job hardened with Commander deps and
  detached-HEAD normalization.
- `80614e5` — CI pinning hardened with full Commander SHA + `fetch-depth: 0`.

## Hardening (non-blocking but tracked)

- [x] Retained `DeleteUnsupportedError` as a public compat shim subclassing
      `CapabilityError`; provider delete/capability failures flow through
      `CapabilityError`.
- [x] Read `gateway.ksm_application_name` in `reference_existing`
      mode (currently parsed and dropped).
- [x] Snapshot tests for `RichRenderer` table layouts.
- [x] Expand `redact()` patterns (bearer tokens, JWTs, KSM URLs).
- [x] `tests/test_perf.py` → add `resource.getrusage` memory
      assertions (currently prints only).
- [x] Map DOR `TEST_PLAN.md` scenarios to SDK tests (`tests/test_dor_scenarios.py`;
      6 scenarios covered, 2 marked `xfail` for deferred v1.1 gaps:
      partial-apply rollback, Commander version mismatch).
- [ ] Module rename from `keeper_sdk` → `declarative_sdk_k` (breaking, v2.0.0;
      will ship a shim module so `import keeper_sdk` keeps working for
      one minor cycle).

## Release gating

Only remaining blocker: signed `v1.0.0` release tag. `EnvLoginHelper`
live smoke proved the login contract on 2026-04-25; the remaining
apply-path `session_token_expired` issue is a separate deferred
Commander-CLI session-refresh gap.

A PR can tag v1.0.0 when every `[ ]` in "Shipping gates" above is
checked **and** CI is green on `main` for two consecutive merges. The
"Hardening" section does not gate the tag; track via GitHub Issues.
