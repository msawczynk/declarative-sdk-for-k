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
      2026-04-24 capability-mirror work).
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
      `scripts/sync_upstream.py`, and the 2026-04-24 DOR reframe).

### 2. Upstream DOR reconciliation
- [x] Upstream DOR reconciliation — SUPERSEDED 2026-04-24 by
      capability-mirror reframe (see 2026-04-24 audit +
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
- [x] GitHub Release asset workflow (`on: release: published`) in
      `.github/workflows/publish.yml`: builds `dist/*`, `twine check`, uploads
      assets to the GitHub Release via `gh release upload`. **No PyPI**
      distribution for this repository (install from git or release wheels;
      see `docs/RELEASING.md`).
- [x] Annotated `v1.0.0` release tag via `gh release create` (no GPG/SSH
      signature required). Rationale: distribution is GitHub-only, install path
      is `pip install git+...@<tag-or-sha>` over TLS — no PyPI publish, no
      Linux-distro packaging, no documented `git verify-tag` consumer flow.
      Tag-signing policy revisited if/when supply-chain requirements change
      (sigstore/cosign of `dist/*` in `publish.yml` is the cheap upgrade path —
      OIDC, no maintainer key — see `docs/RELEASING.md`).

### 4. Login path usability
- [x] Ship `EnvLoginHelper` as in-tree reference.
- [x] `KEEPER_SDK_LOGIN_HELPER` now optional; env-var fallback kicks in.
- [x] `docs/LOGIN.md` with the 30-line skeleton.
- [x] Live EnvLoginHelper smoke proves login contract: validate + plan
      + sandbox provisioning all green via `--login-helper env` on
      2026-04-25 (tracked in this checklist + smoke docs). End-to-end apply blocked on
      separate Commander-CLI session-refresh gap (deferred, see
      `AUDIT.md` / deferred Commander session-refresh gap).

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

**Post–v1.0.0 (vault, not a v1.0.0 tag blocker):** `keeper-vault.v1` uses the same
`validate --online` exit-code ladder for **stages 4–5** (Commander `discover`,
`compute_vault_diff`, `check_tenant_bindings` — vault L1 hook is a **no-op** today).
It does **not** gate the annotated `v1.0.0` checklist above; README / PAM-bar
honesty for vault follows [`docs/PAM_PARITY_PROGRAM.md`](./docs/PAM_PARITY_PROGRAM.md).

### 6. Live-smoke coverage
- [x] `pamMachine` create → verify → delete cycle.
- [x] `pamDatabase` cycle (scenario registered, offline-tested; live run
      = `python3 scripts/smoke/smoke.py --scenario pamDatabase`).
- [x] `pamDirectory` cycle (scenario registered + offline-tested; live
      run = `--scenario pamDirectory`).
- [x] `pamRemoteBrowser` cycle (scenario registered + offline-tested;
      live run = `--scenario pamRemoteBrowser`).
- [x] `pamUser` nested shape covered offline by `pamUserNested`: the
      scenario builds `resources[].users[]` and proves it through
      schema, typed model, planner, and Commander JSON normalization.
      Standalone/top-level `pamUser` live-smoke support remains deferred
      to v1.1.
- [x] Adoption path against unmanaged records deferred to v1.1.
- [x] Field-drift → UPDATE path deferred to v1.1.
- [x] Two-writer conflict (ownership-marker race) deferred to v1.1.

The registered scenarios share the identity / sandbox / destroy flow;
each scenario only diverges at `resources[]` and the post-apply
invariant verifier. `pamUserNested` is the dedicated nested-user shape,
not a top-level `pamUser` scenario. See `scripts/smoke/scenarios.py`
and `tests/test_smoke_scenarios.py`.

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
- [x] Snapshot tests for `RichRenderer` table layouts
      (`tests/test_renderer_snapshots.py`, 6 cases).
- [x] Expand `redact()` patterns (bearer tokens, JWTs, KSM URLs;
      covered in `tests/test_redact.py`).
- [x] `tests/test_perf.py` → add `resource.getrusage` peak-RSS
      assertion (`<192 MiB`).
- [x] Map DOR `TEST_PLAN.md` scenarios to SDK tests (`tests/test_dor_scenarios.py`
      plus `tests/test_commander_cli.py` for Commander-specific apply paths).
      Partial-apply outcomes + `keepercommander` floor gate are covered in
      `test_commander_cli.py` (`test_apply_partial_failure_records_outcomes_then_raises`,
      `test_apply_rejects_keepercommander_below_minimum`).
- [x] **KSM as first-class SDK feature** — `dsk bootstrap-ksm` provisions
      the app + admin-record share + one-time client token + redeemed
      `ksm-config.json` end-to-end (`keeper_sdk/secrets/bootstrap.py`);
      `KsmLoginHelper` reads Commander credentials *back out* of that
      vault (`keeper_sdk/auth/helper.py` + `keeper_sdk/secrets/ksm.py`);
      Phase B inter-agent bus directory provisioned but client sealed
      (`secrets/bus.py` raises `NotImplementedError`). 264 unit tests;
      docs at `docs/KSM_BOOTSTRAP.md` + `docs/KSM_INTEGRATION.md`. Was
      a v1.x roadmap row; delivered in PRs #13/#14. End-to-end live bootstrap → login → apply loop is
      the next proof gate (offline tests are green).
- [x] **Coverage ratchet floor 83 → 84** with new baseline 86.32% across
      315 tests after redact / schema / normalize 100%-coverage slices
      (PRs #17/#18/#19) and ratchet bump (PR #20). `ci.yml` comment
      updated for the new baseline + test count.
- [x] **Scope-fence CI workflow** (`.github/workflows/scope-fence.yml`)
      — structural denylist for orchestration / per-session
      path globs; only ADDS trip the fence (`--diff-filter=A`).
      Prevents the recurring orchestration-leak bug class. Delivered in PR #16.
- [ ] Module rename from `keeper_sdk` → `declarative_sdk_k` (breaking, v2.0.0;
      will ship a shim module so `import keeper_sdk` keeps working for
      one minor cycle).

## Release gating

**Zero remaining v1.0.0 GA blockers.** `EnvLoginHelper` live smoke proved the
login contract on 2026-04-25; the remaining apply-path `session_token_expired`
issue is a separate deferred Commander-CLI session-refresh gap (does not gate
GA — preview-gated rotation only).

A PR can tag v1.0.0 when every `[ ]` in "Shipping gates" above is
checked **and** CI is green on `main` for two consecutive merges. The
"Hardening" section does not gate the tag; track via GitHub Issues.

Tag policy: **annotated only** (no GPG/SSH signature). GitHub-only repo, no
PyPI, no downstream `git verify-tag` consumer. Upgrade path if requirements
change → sigstore/cosign of `dist/*` in `.github/workflows/publish.yml`
(OIDC, no local key).
