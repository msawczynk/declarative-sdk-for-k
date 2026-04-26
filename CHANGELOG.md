# Changelog

All notable changes to `declarative-sdk-for-k` (`dsk`) land here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Vault Commander UPDATE** — after `RecordEditCommand`, require `return_result["update_record_v3"]`
  when the merged v3 JSON still differs from cache data (Commander otherwise logs and returns
  without raising); skip the call when patch yields no net change.

### Changed
- **Docs — vault L1 contracts** — [`docs/VAULT_L1_DESIGN.md`](docs/VAULT_L1_DESIGN.md) §4;
  [`docs/VALIDATION_STAGES.md`](docs/VALIDATION_STAGES.md) (operator caveats + remediation);
  [`AGENTS.md`](AGENTS.md) (vault paragraph after `validate` pointer);
  [`docs/live-proof/README.md`](docs/live-proof/README.md) (caveat links);
  [`README.md`](README.md) (readiness + honest limits + layout tree).
- **Docs — indexes + orchestration** — [`docs/SCAFFOLD.md`](docs/SCAFFOLD.md);
  [`keeper_sdk/providers/SCAFFOLD.md`](keeper_sdk/providers/SCAFFOLD.md);
  [`docs/ORCHESTRATION_PAM_PARITY.md`](docs/ORCHESTRATION_PAM_PARITY.md) (§1 G2–G6 + §3 status pointer + V6 train row);
  [`docs/ORCHESTRATION_UNTIL_COMPLETE.md`](docs/ORCHESTRATION_UNTIL_COMPLETE.md) (§7 checklist, §10, revision log).
- **Docs — parity program + execution plan** — [`docs/PAM_PARITY_PROGRAM.md`](docs/PAM_PARITY_PROGRAM.md)
  (inventory, Phase 0 `validate`, Phase 1a JSON modes);
  [`docs/EXECUTION_PLAN_HEAVY_ORCHESTRATION.md`](docs/EXECUTION_PLAN_HEAVY_ORCHESTRATION.md) (Phase D V6 / L1 vs V8 exit criteria).

### Added
- **V8 prep** — [`docs/live-proof/keeper-vault.v1.sanitized.template.json`](docs/live-proof/keeper-vault.v1.sanitized.template.json)
  (`template: true`, shape-only) plus README section; **§2 ledger** in
  [`docs/ORCHESTRATION_UNTIL_COMPLETE.md`](docs/ORCHESTRATION_UNTIL_COMPLETE.md)
  marks `keeper-vault.v1` **G3–G5** complete (G2 still **◐** until §7 sign-off;
  **G6** open). CI `schema-validate` also runs `python -m json.tool` on
  `docs/live-proof/*.json`. `docs/SCAFFOLD.md` indexes `live-proof/`; regression
  tests in `tests/test_live_proof_artifacts.py`. Sample L1 manifest
  [`examples/scaffold_only/vaultOneLogin.yaml`](examples/scaffold_only/vaultOneLogin.yaml)
  linked from `docs/live-proof/README.md` and **V8** row in `ORCHESTRATION_PAM_PARITY.md`.
- **Master orchestration** — [`docs/ORCHESTRATION_UNTIL_COMPLETE.md`](docs/ORCHESTRATION_UNTIL_COMPLETE.md):
  exit **tiers A/B/C**, per-family **completion ledger** (G0–G6), repeating
  **waves** W.1–W.6, parallelism do/don’t, metrics dashboard, §7 vault +
  program checklist through Tier B.
- **Vault L1** — `docs/VAULT_L1_DESIGN.md` (slice 1 design; sign-off §7 still
  pending) plus **`keeper_sdk/core/vault_models.py`**: `VaultManifestV1`,
  `VaultRecord`, `load_vault_manifest()` with L1 **`login`-only** record rule;
  tests in `tests/test_vault_models.py`.
- **Vault PR-V2** — **`keeper_sdk/core/vault_graph.py`**: `build_vault_graph`,
  `vault_record_apply_order` (duplicate `uid_ref`, `folder_ref` prerequisite
  nodes, invalid `folder_ref` pattern → `RefError`); tests in
  `tests/test_vault_graph.py`.
- **Vault PR-V5/V6 (Commander)** — :class:`~keeper_sdk.providers.commander_cli.CommanderCliProvider`
  ``discover()`` filters to ``login`` when ``manifest_source`` is ``keeper-vault.v1``;
  ``apply_plan()`` uses :meth:`~keeper_sdk.providers.commander_cli.CommanderCliProvider._apply_vault_plan`
  (``RecordAddCommand`` create; ``RecordEditCommand`` + marker for **UPDATE**;
  ``rm`` delete). ``_detect_unsupported_capabilities`` returns ``[]`` for vault manifests.
  Tests in ``tests/test_commander_cli.py``.
- **Vault PR-V4** — **`load_declarative_manifest`** / **`load_declarative_manifest_string`**
  in `keeper_sdk/core/manifest.py` (PAM :class:`~keeper_sdk.core.models.Manifest` or
  :class:`~keeper_sdk.core.vault_models.VaultManifestV1`). CLI **plan** / **diff** /
  **apply** dispatch on family; **validate --json** uses ``vault_offline`` /
  ``vault_online`` for ``keeper-vault.v1`` (``--online`` = Commander discover +
  ``compute_vault_diff`` smoke). **import** stays PAM-only. Tests: `tests/test_cli.py`.
- **Vault PR-V3** — **`keeper_sdk/core/vault_diff.py`**: `compute_vault_diff`
  (reuses PAM diff classification for vault ``records[]``); integration tests with
  existing :class:`~keeper_sdk.providers.mock.MockProvider` in
  `tests/test_vault_mock_provider.py`. CLI family dispatch = PR-V4+.
- **`dsk report` — `--sanitize-uids`** on `password-report`,
  `compliance-report`, and `security-audit-report`: fingerprints
  Base64-style UIDs that appear inside string values. Raw
  `record_uid` (and related) key values stay as returned by Commander
  unless **`--quiet`** is also set (which fingerprints those UID
  fields). See `AGENTS.md` command table.
- **Orchestration** — `docs/NEXT_SPRINT_PARALLEL_ORCHESTRATION.md` adds
  **§12 large-sprint mode** (WIP limits, program board, trains, roles) and
  **§13** sprint-size cheat sheet. **Live access:** docs + `AGENTS.md` now
  state that **granted code** (workers, CI, agents) may run L1 / live-proof
  under the same harness rules as humans; serialization is **per tenant**, not
  parent-only. **§14** plans through this file; **§15** closes capability gaps
  then defines **maintenance mode** (Commander pin / drift, operator-optional);
  **§16** mandates a **daybook review + optimization** after every sprint.
  **Policy:** orchestrator + **Codex CLI** may run live L1/smoke; **pin** never
  ambiguous (resolve with live test + drift-check); **support prose** for
  Commander defers to **upstream** repos; **daybook** = private GitHub +
  `sync_daybook.sh`.   **Orchestrator** explicitly **owns** prerequisite health +
  daybook sync (`AGENTS.md`, `docs/live-proof/README.md`, orchestration header).
  **§0** autonomous cold start: new sessions use repo + daybook, not repeated
  chat prompts.
- **P18b** — `sync_upstream` adds **integrations** groups (`ScimCommand`,
  `AutomatorCommand`) + **trash** `GroupCommand`; vault-related **Command** rows
  (`get`, `search`, `record-add`, `record-update`, `list-sf`, `ls`). Matrix
  sections for P18b + split PAM group table header.
- **P18a** — `scripts/sync_upstream.py` registers six enterprise CLI command
  classes (`enterprise-down` / `-info` / `-node` / `-user` / `-role` / `-team`);
  capability matrix gains **Enterprise commands (extracted, P18a)** section;
  `capability-snapshot.json` expanded accordingly.
- **P18 R1** — `docs/P18_SYNC_UPSTREAM_EXTRACTOR_DECISION.md` (extractor
  expansion: registry model, nesting, phasing P18a–c, risks). `keeper-enterprise`
  `x-keeper-live-proof.evidence` aligned to `docs/live-proof/README.md` (same as
  vault families).
- **Orchestration** — `NEXT_SPRINT` §0 adds explicit **session boundary** note:
  nudges between chats are normal; §0 shortens what each nudge must carry.
  **§0.1** compares queued “continue” heartbeats vs CI / PR / background-agent
  cadence.
- **Live-proof runbook** — `docs/live-proof/README.md` (L1 checklist,
  committed-artifact naming, sanitization expectations). `keeper-vault.v1`
  and `keeper-vault-sharing.v1` now cite it from
  `x-keeper-live-proof.evidence` while status remains `scaffold-only`
  until a transcript JSON is added.
- **KSM as first-class SDK feature** — three new modules in
  `keeper_sdk/secrets/` close the credential loop end-to-end:
  - `bootstrap.py` provisions a Keeper Secrets Manager application,
    shares the Commander admin record into it, generates a one-time
    client token, redeems that token into a local
    `~/.keeper/<app-name>-ksm-config.json`, and verifies the resulting
    KSM client can see the admin-record shape `KsmLoginHelper` expects.
    Exposed as `dsk bootstrap-ksm --app-name … [--admin-record-uid …]
    [--create-admin-record] [--first-access-minutes …] [--unlock-ip]
    [--with-bus] [--login-helper commander|ksm|<path>]`.
  - `ksm.py` ships `KsmSecretStore` (thin façade over
    `keeper_secrets_manager_core.SecretsManager` with field-value
    caching), `KsmLoginCreds` dataclass, and
    `load_keeper_login_from_ksm()` — used by
    `keeper_sdk.auth.KsmLoginHelper` so SDK callers can authenticate
    Commander *from* KSM with no plaintext env vars on the host.
    Resolves the config from `$KEEPER_SDK_KSM_CONFIG`, `$KSM_CONFIG`,
    `~/.keeper/caravan-ksm-config.json`, or
    `~/.keeper/ksm-config.json` (first usable wins). Field-name
    overrides via `KEEPER_SDK_KSM_LOGIN_FIELD` /
    `KEEPER_SDK_KSM_PASSWORD_FIELD` / `KEEPER_SDK_KSM_TOTP_FIELD` /
    `KEEPER_SDK_KSM_CREDS_RECORD_UID`. TOTP normalisation accepts
    both `otpauth://` URIs and bare base32 secrets.
  - `bus.py` is a sealed Phase B skeleton — every public entry point
    raises `CapabilityError` with a precise next-action so
    accidental imports fail loudly. The `bootstrap_ksm_application
    (create_bus_directory=True, …)` flow already provisions the
    on-tenant directory record this module will read/write; that
    contract is frozen and unit-tested. Wire format, CAS semantics,
    and implementation checklist are documented in the module
    docstring.
  - `keeper_sdk.auth.KsmLoginHelper` joins `EnvLoginHelper` as a
    reference `LoginHelper` impl; `keeper_sdk.providers.commander_cli`
    accepts `--login-helper ksm` or `--login-helper /path/to/helper.py`.
  - New docs: `docs/KSM_BOOTSTRAP.md` (operator runbook for
    `dsk bootstrap-ksm`) and `docs/KSM_INTEGRATION.md` (end-to-end
    bootstrap → `ksm-config.json` → `KsmLoginHelper` → SDK story).
  - 264 unit tests across `tests/test_auth_ksm.py`,
    `tests/test_secrets_ksm.py`, `tests/test_bootstrap_ksm.py`, and
    `tests/_fakes/{ksm,commander}.py` (offline-green; live
    bootstrap → login → apply loop is the next gate).
- **Scope-fence CI workflow** (`.github/workflows/scope-fence.yml`) —
  structural denylist that fails on newly-ADDED paths matching the
  orchestration / daybook / per-session globs (union of LESSONS
  `[scope][drift][prevention]` and historical pruning branches).
  `git diff --diff-filter=A` so only ADDS trip the fence;
  modifications to pre-existing tracked files don't fire. Activated
  alongside the regular `lint / typecheck / test / examples /
  drift-check` jobs.
- **Per-module 100% coverage** for three core modules with no API
  changes — `keeper_sdk/core/redact.py`, `keeper_sdk/core/schema.py`,
  `keeper_sdk/core/normalize.py` — via expanded edge-case tests in
  `tests/test_redact.py`, `tests/test_schema.py`,
  `tests/test_normalize.py`. Total suite now 315 tests / 86.32% line
  coverage (was 277 / 85.4%).
- **Cov ratchet floor raised to 84%** in
  `.github/workflows/ci.yml::test` — `pytest --cov-fail-under=84`
  (was 83). Comment block updated for the new baseline (86% across
  3604 LOC / 315 tests). Floor stays at `baseline - 2` so small
  refactors don't gate CI while still catching ~70 LOC regressions.

### Changed
- **Vault Commander `apply_plan` UPDATE** — `_apply_vault_plan` now merges
  planner ``change.after`` into existing v3 record JSON (in-process
  ``RecordEditCommand``) before refreshing the ownership marker; ``custom[]``
  merges preserve the SDK marker when the manifest patch omits it.
- **Report row preprocessing** always applies **secret-key-only**
  redaction to row-shaped data before the existing `redact` pass, so
  Commander fields whose names match known secret keys (for example
  `token`) are replaced with `<redacted>` even when UID fields remain
  visible. Implemented via `sanitize_secret_keys_only` in
  `keeper_sdk/cli/_live/transcript.py` and `prepare_report_rows` in
  `keeper_sdk/cli/_report/common.py`.

### Fixed
- **Vault diff false positives** — ``compute_vault_diff`` compares manifest
  ``login`` ``fields[]`` to Commander-flattened scalar keys (and strips the SDK
  marker from ``custom[]`` compare) so matching tenants do not churn ``UPDATE``;
  tests in ``tests/test_vault_diff.py`` (includes case-insensitive typed-field
  labels vs flattened live keys). ``AGENTS`` / ``VALIDATION_STAGES`` / README
  readiness row + ``examples/scaffold_only/vaultMinimal.yaml`` comment updated.
- **Vault Commander UPDATE** — body sync now requires **record cache
  version 3** only; v6 was incorrectly admitted but Commander's
  ``RecordEditCommand`` ``--data`` path accepts ``rv == 3`` only.
- **Rotation drift resume** — `keeper_sdk/providers/commander_cli.py`
  no longer loops on `session_token_expired` during rotation re-plan
  after a session refresh. The bounded in-process refresh helper now
  walks `__cause__` correctly when the original exception is wrapped
  by Commander's session-management layer; pinned by
  `tests/test_session_refresh_*` regression tests.

### Changed
- `README.md` reconciled against the new `main`: dated 2026-04-26,
  test count 216 → 315, coverage 86.32% (CI floor 84), KSM-as-feature
  surfaced with offline-green / live-gate-pending caveat. Capability
  scope KSM row rewritten to include `dsk bootstrap-ksm` and
  `KsmLoginHelper`. Layout block adds `keeper_sdk/secrets/`, the
  `KsmLoginHelper` mention under `auth/`, `bootstrap-ksm` in the CLI
  list, and `docs/KSM_BOOTSTRAP.md` + `docs/KSM_INTEGRATION.md` in
  the docs index. New "Quick start (KSM bootstrap)" subsection.

### Removed
- In-tree orchestration / Codex CLI stack: `docs/CODEX_CLI.md`,
  `docs/CODEX_GITHUB.md`, `docs/ORCHESTRATION_PHASE0_PARALLEL.md`,
  `scripts/agent/` (the whole tree: `_codex_resolve.sh`,
  `codex_offline_slice.sh`, `codex_live_smoke.sh`, `phase0_gates.sh`,
  `run_parallel_codex.sh`, `run_smoke_matrix.sh`, `prompts/*.prompt.md`,
  READMEs and SCAFFOLD), `.github/codex/prompts/scoped-task.md`,
  `.github/ISSUE_TEMPLATE/codex_task.yml`, and
  `.github/workflows/codex-task.yml`. Cursor / Codex / daybook
  orchestration is now operator-side infrastructure only — maintained
  canonically in the maintainer's private daybook
  (`msawczynk/cursor-daybook`: `docs/orchestration/` + `templates/`).
  Adopters who want the same parent / worker workflow copy templates
  from there with `# adapt:` markers; this repo no longer ships any of
  those files.

### Changed
- `AGENTS.md`, `README.md`, `SCAFFOLD.md`, `.cursorrules`,
  `V1_GA_CHECKLIST.md`, `RECONCILIATION.md`, `AUDIT.md`,
  `docs/SCAFFOLD.md`, `scripts/SCAFFOLD.md`, `scripts/smoke/SCAFFOLD.md`,
  `scripts/smoke/README.md`, `.github/SCAFFOLD.md`,
  `docs/SDK_DA_COMPLETION_PLAN.md`,
  `docs/SDK_COMPLETION_PLAN.md`, and
  `docs/SDK_ORCHESTRATED_FEATURE_COMPLETE.md` reconciled against the
  removal — every link to a deleted path replaced with a thin pointer
  to the operator-side daybook or with the equivalent direct command
  (`pytest`, `ruff`, `mypy`, `python3 scripts/smoke/smoke.py …`).
- `.gitignore` drops `.codex-runs/` (no longer applicable); `.smoke-runs/`
  retained for ad-hoc local logs.

## [1.1.0] - 2026-04-26

Tag policy decision: annotated-only, GitHub-only repo (no PyPI, no `git
verify-tag` consumer flow). Sigstore/cosign of `dist/*` in `publish.yml`
is the cheap upgrade path if supply-chain requirements change.

### Added
- 12 per-folder `SCAFFOLD.md` files under `keeper_sdk/{,core,cli,providers,auth}`,
  `tests/`, `docs/`, `examples/`, `scripts/{,agent,smoke}`, and `.github/`. Each
  provides local module map, hard rules, "where to land new work" table, and
  reconciliation rows so agents landing in any directory get scoped context
  without re-reading the root scaffold.
- `RECONCILIATION.md` — root cross-check vs `V1_GA_CHECKLIST.md`,
  `docs/SDK_DA_COMPLETION_PLAN.md`, `AUDIT.md`, `REVIEW.md`. Records every
  shipped / preview-gated / upstream-gap / deferred row, proves no silent
  drops, lists open questions. Single page agents read before proposing
  new features.
- `CommanderCliProvider.apply_plan()` — runtime `keepercommander` floor check
  (`17.2.13` via `importlib.metadata`) plus `CapabilityError.context["partial_outcomes"]`
  when post-import `discover()`, marker tuning, marker write, or rotation apply
  fails after earlier creates succeeded (offline tests in `test_commander_cli.py`).
- `scripts/agent/run_smoke_matrix.sh` — sequential live run of every smoke
  scenario with `python3 -u` and per-scenario logs under `.smoke-runs/`
  (gitignored); optional `SMOKE_LOGIN_HELPER` / `--login-helper`.
- `docs/SDK_ORCHESTRATED_FEATURE_COMPLETE.md` — orchestration index: SDK_DA
  phases mapped to `phase0_gates.sh`, Codex scripts, live smoke commands, and
  gate-lift stop conditions.

### Fixed
- `scripts/smoke/smoke.py` — post-destroy folder sweep + manifest-empty
  re-discover for verify. Empty-manifest plans omit gateways /
  `pam_configurations`; combined with `reference_existing` scaffolds,
  Commander could leave SDK-marked `pam_configuration` rows under the
  project Resources/Users folders that never appeared as DELETE rows.
  Smoke now sweeps both folders via `sandbox.teardown_records(manager=…)`
  (tolerant of "No such folder" since destroy may have removed the tree)
  and re-discovers with an empty `manifest_source` so `discover()` skips
  the synthetic reference-config `LiveRecord` that always carries the
  marker. Pairs with the manifest-aware RBI discover from `e71fb46`.

### Changed
- `V1_GA_CHECKLIST.md` — drop signed-`v1.0.0`-tag blocker; record
  annotated-only tag policy with rationale (GitHub-only repo, no PyPI,
  no documented `git verify-tag` consumer flow). Sigstore/cosign of
  `dist/*` in `publish.yml` is the upgrade path if supply-chain
  requirements change.
- `SCAFFOLD.md` — refreshed to link the 12 per-folder SCAFFOLDs and
  add new tree entries (`scripts/agent/_codex_resolve.sh`,
  `run_parallel_codex.sh`, `prompts/`, `tests/test_errors.py`,
  `tests/test_rbi_readback.py`); reconciliation row for the `v1.0.0`
  tag flipped `EXTERNAL-GAP` → `SHIPPED-by-policy`.
- `compute_diff` — ``pamUser`` field drift uses semantic equality for
  ``rotation_settings`` (CRON normalization, ``enabled`` bool vs ``on``/``off``,
  extra schedule keys) so live re-plan is not blocked by readback-only shape
  noise; true schedule changes still surface as UPDATE.
- `AGENTS.md` — maintainer grant for autonomous gates + live smoke when lab
  configs exist (no per-step approval); still no secret echo.
- Commander: after reference-existing scaffold, invalidate cached in-process
  `KeeperParams` before `pam project extend` to avoid `session_token_expired`
  on graph APIs; walk `__cause__` when detecting retryable session errors.
- Smoke: fail KSM `share add` when stdout reports folder is not a record/shared
  folder even if rc=0; include stderr/stdout tail on non-zero share failures.
- `docs/COMMANDER.md` — SDK_DA §P3.1 readback bucket vocabulary; runtime
  `keepercommander` floor on `apply_plan()`; Issue #5 RBI dirty-readback status.
- Autonomous orchestration pass: parallel `run_parallel_codex.sh` (slices 01–03)
  aligned GitHub issue template + `CODEX_GITHUB`, smoke README scenario matrix,
  root docs with `ORCHESTRATION_PHASE0_PARALLEL`; parent ran `phase0_gates.sh full`
  + `ruff format` on touched Python.
- RBI discover DAG merge (`allowedSettings` → `pam_settings.options`) now
  delegates to `_merge_rbi_dag_options_into_pam_settings` in
  `_commander_cli_helpers.py`, with unit tests for tri-state / default
  handling. Discover passes `folder_uid` on each `ls` listing row for
  consistent `get` readback metadata. Post-apply smoke passes `manifest_source`
  and `discover()` may bootstrap in-process login when RBI + resources list are
  present so verify can see DAG-backed toggles.

### Added
- Offline P2.1 diff anchor: `test_diff_nested_pam_user_rotation_drift_surfaces_rotation_settings_key` — proves nested `pamUser` rotation readback drift keys `rotation_settings` in plan tails.
- `scripts/agent/_codex_resolve.sh` — auto-pick Codex from `CODEX_BIN`, `PATH`, or newest Cursor `openai.chatgpt-*` extension bundle.
- `scripts/agent/run_parallel_codex.sh` + `scripts/agent/prompts/*.prompt.md` — disjoint Codex CLI slices with logs under `.codex-runs/` (gitignored).
- `docs/ORCHESTRATION_PHASE0_PARALLEL.md` + `scripts/agent/phase0_gates.sh` — parent vs Codex split, Phase 0 / merge gates scripted (referenced from global Cursor rules + daybook drift-guard).
- `pamUserNested` smoke scenario — proves nested `resources[].users[]`
  through schema, typed model, planner, and Commander normalization
  without claiming standalone top-level `pamUser` live support.
- Offline `pam rotation edit` argv mapping helper and stricter preview
  detection for rotation keys. Rotation remains preview/unsupported
  until live apply is proven.
- Offline post-import tuning apply wiring for a safe subset of
  `pam connection edit` and `pam rbi edit` fields. `apply_plan()` now
  resolves changed records after rediscovery, executes the mapped edit
  argv via `_run_cmd()`, and exposes dry-run preview argv without running
  tuning commands. Live tenant proof is still pending.
- Bounded in-process Commander session refresh for `session_token_expired`
  during `pam project import` / `extend` and ownership-marker writes.
  This is unit-tested with synthetic exceptions and live-proven through
  `scripts/smoke/smoke.py --login-helper env --scenario pamMachine`.
- In-process PAM gateway/config JSON listing for the Commander provider,
  with `sync_down` and bounded session refresh. This avoids stale
  subprocess Commander sessions during reference-existing apply.
- `docs/SDK_COMPLETION_PLAN.md` — devil's-advocate completion plan for
  parent orchestration plus Codex worker slices.
- Smoke-runner diagnostics now identify the active SDK auth path and
  preserve command, exit code, stdout tail, and stderr tail on SDK
  subprocess failures.
- Pure `build_pam_rotation_edit_argvs()` resolver for nested `pamUser`
  rotation settings. It resolves user/resource/config/admin refs and is
  used only by the experimental apply path while rotation remains gated.
- Experimental Commander apply wiring for nested
  `resources[].users[].rotation_settings`, guarded by
  `DSK_EXPERIMENTAL_ROTATION_APPLY=1`. The public provider conflict
  remains closed by default pending parent live proof.
- `docs/ISSUE_6_JIT_SUPPORT_BOUNDARY.md` — source-backed JIT decision:
  keep `jit_settings` preview-gated because pinned Commander has import
  and launch helpers, but no safe standalone edit surface.
- `docs/ISSUE_7_GATEWAY_CREATE_PROJECTS_DESIGN.md` — docs-only design
  for gateway `mode: create` and top-level `projects[]`; preview gates
  remain closed until Commander hooks and live proof are available.
- `docs/COMMANDER.md` post-import tuning field map for connection/RBI
  fields, marking import-supported, helper-only, and unsupported/unknown
  cases.
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
