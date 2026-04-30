# SCAFFOLD

## Purpose (1 line)
Agent-first Python SDK + CLI (`dsk`) for deterministic `validate -> plan -> apply` of Keeper tenant state, with mock-first tests and Commander-backed live coverage.

## Per-folder scaffolds (agents: start here when you land in a folder)

| Folder | Scaffold | Purpose |
|---|---|---|
| `keeper_sdk/` | [`keeper_sdk/SCAFFOLD.md`](./keeper_sdk/SCAFFOLD.md) | Package overview + sub-package map + invariants |
| `keeper_sdk/core/` | [`keeper_sdk/core/SCAFFOLD.md`](./keeper_sdk/core/SCAFFOLD.md) | Pure logic — manifest/schema/graph/diff/planner/redact/preview |
| `keeper_sdk/cli/` | [`keeper_sdk/cli/SCAFFOLD.md`](./keeper_sdk/cli/SCAFFOLD.md) | `dsk` Click entrypoint + Rich renderer + exit codes |
| `keeper_sdk/providers/` | [`keeper_sdk/providers/SCAFFOLD.md`](./keeper_sdk/providers/SCAFFOLD.md) | Mock + Commander provider; capability gates |
| `keeper_sdk/auth/` | [`keeper_sdk/auth/SCAFFOLD.md`](./keeper_sdk/auth/SCAFFOLD.md) | `EnvLoginHelper` + helper-protocol contract |
| `keeper_sdk/secrets/` | [`keeper_sdk/secrets/SCAFFOLD.md`](./keeper_sdk/secrets/SCAFFOLD.md) | KSM bootstrap + `ksm` reader + bus skeleton |
| `tests/` | [`tests/SCAFFOLD.md`](./tests/SCAFFOLD.md) | Per-test-file inventory + where to land new tests |
| `docs/` | [`docs/SCAFFOLD.md`](./docs/SCAFFOLD.md) | Doc inventory + audience + ownership; product queue: [`DSK_NEXT_WORK.md`](./docs/DSK_NEXT_WORK.md) |
| `scripts/` | [`scripts/SCAFFOLD.md`](./scripts/SCAFFOLD.md) | Smoke, daybook harness (forwarder), phase_harness, sync — top-level map |
| `scripts/daybook/` | [`scripts/daybook/SCAFFOLD.md`](./scripts/daybook/SCAFFOLD.md) | `harness.sh` → `~/.cursor-daybook-sync`; tests in `tests/test_daybook_harness.py` |
| `scripts/smoke/` | [`scripts/smoke/SCAFFOLD.md`](./scripts/smoke/SCAFFOLD.md) | Live-smoke harness + scenario registry |
| `examples/` | [`examples/SCAFFOLD.md`](./examples/SCAFFOLD.md) | Canonical minimal manifests + CI contract |
| `.github/` | [`.github/SCAFFOLD.md`](./.github/SCAFFOLD.md) | Workflows + issue templates |

Reconciliation against `V1_GA_CHECKLIST.md` + `docs/SDK_DA_COMPLETION_PLAN.md` +
`AUDIT.md` + `REVIEW.md` lives in [`RECONCILIATION.md`](./RECONCILIATION.md).

## Current baseline

- **v1.3.0.dev0 local gates:** 1037 tests / 87% coverage.
- **Phase 7:** in progress for broader Keeper surface: shared-folder Commander create/update is wired, KSM bus is documented as a sealed stub, and KSM app create/reference, teams/roles read-only validate, and report hardening remain tracked.
- **New Phase 7 / v1.2-v1.3 tests:** `tests/test_ksm_app_create.py`, `tests/test_teams_roles_validate.py`, `tests/test_report_commands.py`, `tests/test_vault_custom_fields.py`, `tests/test_vault_update_smoke.py`, `tests/test_adoption_smoke.py`, `tests/test_two_writer.py`, `tests/test_msp_apply.py`, `tests/test_vault_shared_folder.py`, `tests/test_ksm_app_reference.py`, `tests/test_shared_folder_model.py`, `tests/test_shared_folder_commander.py`, `tests/test_ksm_bus_stub.py`, `tests/test_compat_shim.py`.
- **New examples:** `examples/vault/login-record.yaml`, `examples/vault/shared-folder.yaml`, `examples/msp/02-with-modules.yaml`.
- **Import-path rename:** `declarative_sdk_k` forward-compatible shim is present; `keeper_sdk` remains the v1.x canonical package and removal stays deferred to v2.0.

## Tree

Tree snapshot: refresh when layout shifts; exact commit: `git rev-parse HEAD`. Deeper per-area maps: `keeper_sdk/SCAFFOLD.md`, `docs/SCAFFOLD.md`, `tests/SCAFFOLD.md`. Full file list: `git ls-files`.

```text
.
├── .commander-pin                          # Pinned Commander SHA for drift-check CI + docs sync.
├── .cursorrules                            # Local editor/agent rule entrypoint.
├── .github/                                # GitHub automation root.
│   └── workflows/
│       ├── ci.yml                          # CI: lint, mypy, pytest, examples, drift-check, build.
│       ├── live-smoke.yml                  # Optional live tenant (secrets-backed).
│       ├── publish.yml                     # GitHub Release: build dist/* + upload assets (no PyPI).
│       └── scope-fence.yml                 # Blocks operator-only doc paths on PRs.
├── .gitignore                              # Git ignore rules.
├── AGENTS.md                               # Machine-readable operating manual for agents.
├── AUDIT.md                                # Milestone/audit history and design reconciliation log.
├── CHANGELOG.md                            # Keep-a-Changelog release notes.
├── LICENSE                                 # MIT license.
├── README.md                               # Human-oriented overview, install, status, quick start.
├── REVIEW.md                               # Devil's-advocate review notes and deferred work.
├── SECURITY.md                             # Security reporting policy.
├── V1_GA_CHECKLIST.md                      # Blocking v1.0.0 checklist and hardening backlog.
├── docs/                                   # Focused docs for operator and agent workflows.
│   ├── CAPABILITY_MATRIX.md                # Generated Commander capability mirror.
│   ├── COMMANDER.md                        # Version pin, CLI/API usage, drift policy, post-import tuning field map.
│   ├── ISSUE_6_JIT_SUPPORT_BOUNDARY.md     # JIT apply boundary decision against pinned Commander.
│   ├── ISSUE_7_GATEWAY_CREATE_PROJECTS_DESIGN.md # Gateway create / projects[] design boundary.
│   ├── LOGIN.md                            # `EnvLoginHelper` + custom login-helper contract.
│   ├── RELEASING.md                        # Maintainer release ritual (GitHub-only; no PyPI).
│   ├── SDK_DA_COMPLETION_PLAN.md           # Devil's-advocate completion gates, phases, and stop conditions.
│   ├── SDK_COMPLETION_PLAN.md              # Roadmap and risk gates for completing SDK support.
│   ├── DSK_NEXT_WORK.md                    # In-repo product priority queue (live + phase harness pointers).
│   ├── VALIDATION_STAGES.md                # Stage-by-stage `validate --online` contract.
│   ├── capability-snapshot.json            # Machine-readable mirror consumed by drift-check CI.
│   └── …                                   # KSM / vault / sharing / MSP / V2 / live-proof — `docs/SCAFFOLD.md`.
├── examples/                               # Canonical minimal manifests for common PAM resource shapes.
│   ├── pamDatabase.yaml                    # Minimal database example.
│   ├── pamDirectory.yaml                   # Minimal directory example.
│   ├── pamMachine.yaml                     # Minimal machine example.
│   ├── pamRemoteBrowser.yaml               # Minimal remote-browser example.
│   ├── msp/02-with-modules.yaml            # MSP modules/addons example.
│   ├── vault/login-record.yaml             # Minimal keeper-vault login record example.
│   ├── vault/shared-folder.yaml            # Phase 7 keeper-vault shared-folder placeholder.
│   ├── sharing*.yaml / vault*.yaml         # Additional corpus (sharing, vault L1) — see `examples/SCAFFOLD.md`.
│   └── scaffold_only/                      # Narrow fixtures for tests / docs.
├── keeper_sdk/                             # Stable 1.x import path; packaged SDK source.
│   ├── __init__.py                         # Package exports/version surface.
│   ├── auth/                               # Login helper protocol + env-backed implementation.
│   │   ├── __init__.py                     # Auth package exports.
│   │   └── helper.py                       # `EnvLoginHelper` + `KsmLoginHelper` + helper contract wiring.
│   ├── secrets/                            # KSM bootstrap, `ksm.py` reader, inter-agent bus (skeleton).
│   │   ├── bootstrap.py / ksm.py / bus.py  # `bootstrap-ksm` + KSM cred path + sealed bus.
│   ├── cli/                                # `dsk` entrypoint + Rich renderer.
│   │   ├── __init__.py                     # CLI package export.
│   │   ├── __main__.py                     # `python -m keeper_sdk.cli` shim.
│   │   ├── main.py                         # Click commands + exit-code orchestration.
│   │   ├── renderer.py                     # Human-readable tables and summaries.
│   │   ├── _report/                        # `dsk report password|compliance|security-audit` subprocess wrappers.
│   │   └── _live/                          # Live runbook / transcript helpers (`live-smoke` support).
│   ├── core/                               # Pure manifest/schema/graph/diff/planner logic.
│   │   ├── __init__.py                     # Core exports.
│   │   ├── diff.py / vault_diff.py         # PAM + vault diffs.
│   │   ├── msp_diff.py / msp_graph.py / msp_models.py  # `msp-environment.v1` (discover/plan; apply/import out of band).
│   │   ├── sharing_diff.py / sharing_models.py  # `keeper-vault-sharing.v1` diff surface.
│   │   ├── errors.py                       # Structured error taxonomy.
│   │   ├── graph.py / vault_graph.py        # PAM + vault dep DAGs.
│   │   ├── interfaces.py                   # Public protocols / typed interfaces.
│   │   ├── manifest.py                     # Load/dump/canonical manifest handling.
│   │   ├── metadata.py                     # Ownership marker encode/decode + timestamps.
│   │   ├── models.py / vault_models.py     # Pydantic models (PAM + vault L1).
│   │   ├── normalize.py                    # Manifest ↔ Commander payload normalization.
│   │   ├── planner.py                      # Plan builder and summary accounting.
│   │   ├── preview.py                      # Preview-key guard (`DSK_PREVIEW=1`).
│   │   ├── redact.py                       # Redaction helpers for plans/diffs/errors.
│   │   ├── rules.py                        # Semantic validation rules beyond JSON schema.
│   │   ├── schema.py                       # JSON-schema loading and validation helpers.
│   │   └── schemas/                        # Packaged JSON schemas (`pam-environment.v1`, …).
│   └── providers/                          # Provider implementations and Commander helpers.
│       ├── __init__.py                     # Provider exports.
│       ├── _commander_cli_helpers.py       # Extracted pure helpers for Commander provider.
│       ├── commander_cli.py                # Live Keeper provider via Commander CLI/API.
│       └── mock.py                         # Offline mock provider used by tests/examples CI.
├── pyproject.toml                          # Packaging, deps, scripts, lint/type/test config.
├── scripts/                                # Maintenance and live-smoke tooling.
│   ├── daybook/                            # `harness.sh` forwards to ~/.cursor-daybook-sync; no JOURNAL in-tree.
│   ├── phase_harness/                      # Local ruff/mypy/pytest + example phase_runner YAML.
│   ├── smoke/                              # Live-smoke harness and scenario registry.
│   │   ├── .commander-config-testuser2.json# Local smoke helper config fixture.
│   │   ├── .gitignore                      # Keeps local smoke secrets/config out of git.
│   │   ├── README.md                       # How to run smoke scenarios.
│   │   ├── __init__.py                     # Smoke package marker.
│   │   ├── identity.py                     # Tenant identity helpers.
│   │   ├── parallel_guard.py               # Profile lock + disjoint Commander config preflight.
│   │   ├── profiles/                       # `DSK_SMOKE_PROFILE` JSON examples (`.gitignore` for local).
│   │   ├── sandbox.py                      # Ephemeral tenant/scaffold helpers.
│   │   ├── scenarios.py                    # Registered live-smoke scenarios by resource type.
│   │   └── smoke.py                        # End-to-end smoke runner CLI.
│   └── sync_upstream.py                    # Regenerates Commander capability mirror.
└── tests/                                  # Offline/unit/contract + optional live harness tests.
    ├── __init__.py                         # Tests package marker.
    ├── conftest.py                         # Shared fixtures and test helpers.
    ├── _fakes/                             # Commander/KSM fakes for narrow tests.
    ├── live/                               # Opt-in live KSM/bootstrap smoke (`pytest tests/live/ -m live`).
    ├── fixtures/                           # Vendored fixture data for clean CI runs.
    │   ├── examples/                       # Copied example corpus used by tests.
    │   ├── profiles/                        # Smoke profile JSON fixtures.
    │   └── renderer_snapshots/              # Rich table snapshots.
    ├── test_*.py                           # 50+ modules — see `tests/SCAFFOLD.md` (vault, sharing, MSP, KSM, CLI cov splits).
    └── …                                   # PAM: `test_diff`, `test_planner`, `test_stage_5_bindings`, …; vault/sharing/MSP: dedicated `test_*` files.
```

## Where to land new work

- **Orchestration narrative / sprint memos / codex prompts:** daybook (`~/.cursor-daybook-sync/docs/orchestration/dsk/`), NOT this repo's `docs/`. **Index + merge gate row:** root [`AGENTS.md`](./AGENTS.md) § “Where orchestration lives”. Do not add `docs/ORCHESTRATION_*` (CI scope-fence).

| Change | Land here | Copy this sibling first |
|---|---|---|
| New resource type | `keeper_sdk/core/models.py` + `keeper_sdk/core/normalize.py` + `scripts/smoke/scenarios.py` | `pamRemoteBrowser` in the same files |
| New provider | `keeper_sdk/providers/<provider>.py` | `keeper_sdk/providers/mock.py` |
| New validate stage | `keeper_sdk/cli/main.py` + `docs/VALIDATION_STAGES.md` | Stage 5 path in `keeper_sdk/cli/main.py` / `tests/test_stage_5_bindings.py` |
| New CLI command | `keeper_sdk/cli/main.py` | `import` command in `keeper_sdk/cli/main.py` |
| New test | `tests/test_<area>.py` | `tests/test_smoke_scenarios.py` or nearest area-specific sibling |
| New example manifest | `examples/<name>.yaml` | `examples/pamMachine.yaml` |
| New doc | `docs/<TOPIC>.md` | `docs/LOGIN.md` |
| New live-smoke scenario | `scripts/smoke/scenarios.py` + `tests/test_smoke_scenarios.py` | `pamDirectory` scenario in both files |

## Reconciliation vs design requirements

| Checklist area | Requirement | Status | Evidence in tree |
|---|---|---|---|
| 1. Capability parity | Preview/decision guard for unsupported schema surface exists | SHIPPED | `keeper_sdk/core/preview.py`, `tests/test_preview_gate.py`, `V1_GA_CHECKLIST.md` |
| 1. Capability parity | Examples exist and CI validates them offline + mock-plans them | SHIPPED | `examples/*.yaml`, `.github/workflows/ci.yml`, `tests/test_smoke_scenarios.py` |
| 1. Capability parity | `pam_configuration_uid_ref` in-manifest linking shipped; cross-manifest/live-tenant config linking fails at stage 3 | SHIPPED | `tests/test_uid_ref_gate.py`, `V1_GA_CHECKLIST.md` |
| 1. Capability parity | Upstream DOR mismatch handled by capability mirror, not the old merge note flow | SHIPPED | `docs/CAPABILITY_MATRIX.md`, `docs/capability-snapshot.json`, `scripts/sync_upstream.py`, `docs/COMMANDER.md` |
| 1. Capability parity | JIT settings support boundary investigated against pinned Commander; no safe post-import writer path confirmed | DEFERRED-1.2 | `docs/ISSUE_6_JIT_SUPPORT_BOUNDARY.md`, `keeper_sdk/core/preview.py`, `keeper_sdk/providers/commander_cli.py` |
| 1. Capability parity | Gateway `mode: create` and top-level `projects[]` design captured; no support gate removed | DESIGN-ONLY | `docs/ISSUE_7_GATEWAY_CREATE_PROJECTS_DESIGN.md`, `keeper_sdk/core/preview.py`, `tests/test_preview_gate.py` |
| 2. DOR reconciliation | Old “merge NOTES_FROM_SDK upstream” checklist is superseded by shipped mirror/drift model | SHIPPED | `AUDIT.md`, `REVIEW.md`, `docs/COMMANDER.md`, `docs/CAPABILITY_MATRIX.md` |
| 3. CI + release | CI matrix, examples job, drift-check, build wiring are live | SHIPPED | `.github/workflows/ci.yml`, `pyproject.toml` |
| 3. CI + release | First green `main` CI run recorded | SHIPPED | `V1_GA_CHECKLIST.md`, `CHANGELOG.md`, commit `fb6fb8b` in `git log` |
| 3. CI + release | GitHub Release asset workflow (`publish.yml`); no PyPI | SHIPPED | `.github/workflows/publish.yml`, `docs/RELEASING.md` |
| 3. CI + release | `v1.0.0` GitHub release exists; annotated tag only, no GPG/SSH signature | SHIPPED-by-policy | GitHub-only repo, no PyPI / no downstream `git verify-tag` flow; tag-signing not required (decision recorded 2026-04-26 in `V1_GA_CHECKLIST.md` + `RECONCILIATION.md`) |
| 4. Login | Built-in env helper + helper contract docs shipped | SHIPPED | `keeper_sdk/auth/helper.py`, `docs/LOGIN.md`, `README.md` |
| 4. Login | Live-smoke explicitly using `EnvLoginHelper` proved full apply session refresh path for `pamMachine` | SHIPPED | `scripts/smoke/smoke.py --login-helper env --scenario pamMachine`, `scripts/smoke/README.md`, `docs/LOGIN.md` |
| 4. Login | KSM bootstrap + `KsmLoginHelper` live (wider loop) | SUPPORTED — `pamMachine` smoke PASSED end-to-end (2026-04-28). Profile: `~/.config/dsk/profiles/default.json` + `~/.keeper/ksm-config.json`. Testuser2 reuse path from admin vault record. | `docs/LIVE_TEST_RUNBOOK.md`, `tests/live/test_ksm_bootstrap_smoke.py` |
| 5. Validate stages | Stage-5 tenant-binding checks implemented + documented | SHIPPED | `keeper_sdk/core/interfaces.py`, `keeper_sdk/providers/commander_cli.py`, `tests/test_stage_5_bindings.py`, `docs/VALIDATION_STAGES.md` |
| 5. Post-import tuning | `pamRemoteBrowser` E2E live smoke PASSED (2026-04-28); `url` = import-supported; DAG-backed `pam_settings.options` = edit-supported-clean when in-process session + graph present; list/audio subfields = edit-supported-dirty. P3.1 bucket table in `docs/COMMANDER.md`. Nested-rotation DAG write / P2.1 = upstream-gap (Commander cannot write rotation `pam_settings`; live confirmed 2026-04-28). | PARTLY-SUPPORTED | `docs/COMMANDER.md` §P3.1, `docs/live-proof/*rbi*.sanitized.json`, `tests/test_rbi_readback.py`, `keeper_sdk/providers/commander_cli.py` |
| 6. Live-smoke coverage | `pamMachine` / `pamDatabase` / `pamDirectory` / `pamRemoteBrowser` scenario registry shipped | SHIPPED | `scripts/smoke/scenarios.py`, `scripts/smoke/smoke.py`, `tests/test_smoke_scenarios.py` |
| 6. Live-smoke coverage | Nested `pamUser` smoke shape shipped; standalone top-level `pamUser` remains unsupported | PREVIEW-GATED | `scripts/smoke/scenarios.py`, `tests/test_smoke_scenarios.py`, `docs/SDK_COMPLETION_PLAN.md` |
| 6. Live-smoke coverage | Nested `pamUser` rotation (P2.1): offline diff fix proven in `diff.py`; live Commander path cannot converge rotation `pam_settings`. | UPSTREAM-GAP (live confirmed 2026-04-28) — Re-plan exit 2 after apply; Commander cannot write `pam_settings` rotation fields. Offline diff fix proven. No SDK code change possible until Commander upstream fix. | `scripts/smoke/scenarios.py`, `keeper_sdk/core/diff.py`, `docs/SDK_DA_COMPLETION_PLAN.md` |
| 6. Live-smoke coverage | Adoption / field-drift / two-writer smokes | SHIPPED v1.1 (offline) | `tests/test_adoption_smoke.py`, `tests/test_vault_update_smoke.py`, `tests/test_two_writer.py` |
| Hardening | Dead `DeleteUnsupportedError` export/catches removed; provider failures use `CapabilityError` | SHIPPED | `keeper_sdk/cli/main.py`, `keeper_sdk/core/errors.py`, `tests/` |
| Hardening | `gateway.ksm_application_name` in `reference_existing` enforced in tenant validation | SHIPPED | `V1_GA_CHECKLIST.md`, `keeper_sdk/providers/commander_cli.py`, `tests/test_stage_5_bindings.py` |
| Hardening | Renderer snapshots, redact expansion, perf memory assertions shipped | SHIPPED | `tests/test_renderer_snapshots.py`, `tests/test_redact.py`, `tests/test_perf.py`, `keeper_sdk/core/redact.py` |
| Phase 7 | Shared folders, KSM app create/reference, teams/roles validate, report command hardening, and example manifests | IN PROGRESS | `tests/test_vault_shared_folder.py`, `tests/test_ksm_app_create.py`, `tests/test_ksm_app_reference.py`, `tests/test_teams_roles_validate.py`, `tests/test_report_commands.py`, `examples/vault/login-record.yaml`, `examples/vault/shared-folder.yaml`, `examples/msp/02-with-modules.yaml` |
| Hardening | DOR `TEST_PLAN` scenario mapping shipped; `declarative_sdk_k` shim landed while `keeper_sdk` removal remains v2 | MIXED | `tests/test_dor_scenarios.py`, `tests/test_compat_shim.py`, `V1_GA_CHECKLIST.md`, `pyproject.toml`, `keeper_sdk/__init__.py`, `declarative_sdk_k/__init__.py` |

## Open questions for next session

- `keeper-pam-declarative` — push to a GitHub remote as the public mirror, or keep local-only? Public makes the drift-check debuggable by third parties; local keeps the marker-wire-format surface unpublished.
- `sdk-live-smoke` branch still carries old `pamform`-era history — rename / delete / leave as snapshot?
- `DSK_PREVIEW=1` discoverability — is a one-line check-list in the `validate` error enough, or does it deserve a dedicated doc page?
- Gateway `mode: create` and `projects[]` — design exists; implementation still needs Commander source audit, provider conflict hardening for `projects[]`, and live proof before any gate lift.
- Post-import RBI tuning — **RESOLVED (2026-04-28)**: `pamRemoteBrowser` E2E smoke passed; `_enrich_pam_remote_browser_dag_options` merges DAG `allowedSettings` → `pam_settings.options`; P3.1 bucket table in `docs/COMMANDER.md`; dirty/list/audio subfields stay bucketed per DA plan. GitHub #5 closeout = maintainer action.
- KSM live loop (`KsmLoginHelper` + profile smoke) — **RESOLVED**: smoke PASSED 2026-04-28 (paths + evidence in reconciliation table row).
- Nested `pamUser` rotation / P2.1 re-plan — **UPSTREAM-GAP**: Commander CLI limitation (cannot write rotation `pam_settings`; re-plan exit 2 after apply). Offline diff fix proven. No SDK change until upstream Commander fix.
