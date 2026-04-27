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
| `docs/` | [`docs/SCAFFOLD.md`](./docs/SCAFFOLD.md) | Doc inventory + audience + ownership |
| `scripts/` | [`scripts/SCAFFOLD.md`](./scripts/SCAFFOLD.md) | Smoke + sync top-level map |
| `scripts/smoke/` | [`scripts/smoke/SCAFFOLD.md`](./scripts/smoke/SCAFFOLD.md) | Live-smoke harness + scenario registry |
| `examples/` | [`examples/SCAFFOLD.md`](./examples/SCAFFOLD.md) | Canonical minimal manifests + CI contract |
| `.github/` | [`.github/SCAFFOLD.md`](./.github/SCAFFOLD.md) | Workflows + issue templates |

Reconciliation against `V1_GA_CHECKLIST.md` + `docs/SDK_DA_COMPLETION_PLAN.md` +
`AUDIT.md` + `REVIEW.md` lives in [`RECONCILIATION.md`](./RECONCILIATION.md).

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
│   ├── VALIDATION_STAGES.md                # Stage-by-stage `validate --online` contract.
│   ├── capability-snapshot.json            # Machine-readable mirror consumed by drift-check CI.
│   └── …                                   # KSM / vault / sharing / MSP / V2 / live-proof — `docs/SCAFFOLD.md`.
├── examples/                               # Canonical minimal manifests for common PAM resource shapes.
│   ├── pamDatabase.yaml                    # Minimal database example.
│   ├── pamDirectory.yaml                   # Minimal directory example.
│   ├── pamMachine.yaml                     # Minimal machine example.
│   ├── pamRemoteBrowser.yaml               # Minimal remote-browser example.
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

- **Orchestration narrative / sprint memos / codex prompts:** daybook (`~/.cursor-daybook-sync/docs/orchestration/dsk/`), NOT this repo's `docs/`. Sprint 7h-47 closeout migrated 6 docs + entire `sprint-memos/` tree out; do not re-land them here.

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
| 5. Validate stages | Stage-5 tenant-binding checks implemented + documented | SHIPPED | `keeper_sdk/core/interfaces.py`, `keeper_sdk/providers/commander_cli.py`, `tests/test_stage_5_bindings.py`, `docs/VALIDATION_STAGES.md` |
| 5. Post-import tuning | Connection/RBI manifest fields audited and offline apply-wired; live RBI proof exposed readback gap, so support remains preview-gated | PREVIEW-GATED | `docs/COMMANDER.md`, `docs/SDK_COMPLETION_PLAN.md`, `keeper_sdk/providers/commander_cli.py`, `tests/test_commander_cli.py` |
| 6. Live-smoke coverage | `pamMachine` / `pamDatabase` / `pamDirectory` / `pamRemoteBrowser` scenario registry shipped | SHIPPED | `scripts/smoke/scenarios.py`, `scripts/smoke/smoke.py`, `tests/test_smoke_scenarios.py` |
| 6. Live-smoke coverage | Nested `pamUser` smoke shape shipped; standalone top-level `pamUser` remains unsupported | PREVIEW-GATED | `scripts/smoke/scenarios.py`, `tests/test_smoke_scenarios.py`, `docs/SDK_COMPLETION_PLAN.md` |
| 6. Live-smoke coverage | Nested `pamUser` rotation smoke is experimental; latest live run applied and verified markers, but post-apply re-plan still reports update drift | PREVIEW-GATED | `scripts/smoke/scenarios.py`, `keeper_sdk/providers/commander_cli.py`, `tests/test_commander_cli.py` |
| 6. Live-smoke coverage | Adoption / field-drift / two-writer smokes not shipped yet | DEFERRED-1.1 | `V1_GA_CHECKLIST.md`, `scripts/smoke/scenarios.py` |
| Hardening | Dead `DeleteUnsupportedError` export/catches removed; provider failures use `CapabilityError` | SHIPPED | `keeper_sdk/cli/main.py`, `keeper_sdk/core/errors.py`, `tests/` |
| Hardening | `gateway.ksm_application_name` in `reference_existing` enforced in tenant validation | SHIPPED | `V1_GA_CHECKLIST.md`, `keeper_sdk/providers/commander_cli.py`, `tests/test_stage_5_bindings.py` |
| Hardening | Renderer snapshots, redact expansion, perf memory assertions shipped | SHIPPED | `tests/test_renderer_snapshots.py`, `tests/test_redact.py`, `tests/test_perf.py` |
| Hardening | DOR `TEST_PLAN` scenario mapping shipped with two expected v1.1 deferrals; `keeper_sdk` rename remains v2 | MIXED | `tests/test_dor_scenarios.py`, `V1_GA_CHECKLIST.md`, `pyproject.toml`, `keeper_sdk/__init__.py` |

## Open questions for next session

- `keeper-pam-declarative` — push to a GitHub remote as the public mirror, or keep local-only? Public makes the drift-check debuggable by third parties; local keeps the marker-wire-format surface unpublished.
- `sdk-live-smoke` branch still carries old `pamform`-era history — rename / delete / leave as snapshot?
- `DSK_PREVIEW=1` discoverability — is a one-line check-list in the `validate` error enough, or does it deserve a dedicated doc page?
- Gateway `mode: create` and `projects[]` — design exists; implementation still needs Commander source audit, provider conflict hardening for `projects[]`, and live proof before any gate lift.
- Post-import connection/RBI tuning — live `pamRemoteBrowser` smoke created records but failed verifier because RBI DAG state is not read back through `discover()`; design readback/re-plan semantics before upgrading preview-gated support.
- Nested `pamUser` rotation — live smoke now gets through `pam rotation edit` and marker verification; keep gates until post-apply readback produces a clean re-plan and destroy cleanup passes.
