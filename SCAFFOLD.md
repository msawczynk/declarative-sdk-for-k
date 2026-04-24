# SCAFFOLD

## Purpose (1 line)
Agent-first Python SDK + CLI (`dsk`) for deterministic `validate -> plan -> apply` of Keeper tenant state, with mock-first tests and Commander-backed live coverage.

## Tree

`tree` absent locally; annotated from `find . -maxdepth 3` using the same ignore set.

```text
.
├── .commander-pin                          # Pinned Commander SHA for drift-check CI + docs sync.
├── .cursorrules                            # Local editor/agent rule entrypoint.
├── .github/                                # GitHub automation root.
│   └── workflows/
│       └── ci.yml                          # CI: lint, mypy, pytest, examples, drift-check, build.
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
│   ├── COMMANDER.md                        # Version pin, CLI/API usage, drift policy.
│   ├── LOGIN.md                            # `EnvLoginHelper` + custom login-helper contract.
│   ├── VALIDATION_STAGES.md                # Stage-by-stage `validate --online` contract.
│   └── capability-snapshot.json            # Machine-readable mirror consumed by drift-check CI.
├── examples/                               # Canonical minimal manifests for common PAM resource shapes.
│   ├── pamDatabase.yaml                    # Minimal database example.
│   ├── pamDirectory.yaml                   # Minimal directory example.
│   ├── pamMachine.yaml                     # Minimal machine example.
│   └── pamRemoteBrowser.yaml               # Minimal remote-browser example.
├── keeper_sdk/                             # Stable 1.x import path; packaged SDK source.
│   ├── __init__.py                         # Package exports/version surface.
│   ├── auth/                               # Login helper protocol + env-backed implementation.
│   │   ├── __init__.py                     # Auth package exports.
│   │   └── helper.py                       # `EnvLoginHelper` loader + helper contract wiring.
│   ├── cli/                                # `dsk` entrypoint + Rich renderer.
│   │   ├── __init__.py                     # CLI package export.
│   │   ├── __main__.py                     # `python -m keeper_sdk.cli` shim.
│   │   ├── main.py                         # Click commands + exit-code orchestration.
│   │   └── renderer.py                     # Human-readable tables and summaries.
│   ├── core/                               # Pure manifest/schema/graph/diff/planner logic.
│   │   ├── __init__.py                     # Core exports.
│   │   ├── diff.py                         # Change classification and diff helpers.
│   │   ├── errors.py                       # Structured error taxonomy.
│   │   ├── graph.py                        # Dependency graph + topo ordering.
│   │   ├── interfaces.py                   # Public protocols / typed interfaces.
│   │   ├── manifest.py                     # Load/dump/canonical manifest handling.
│   │   ├── metadata.py                     # Ownership marker encode/decode + timestamps.
│   │   ├── models.py                       # Pydantic models for the manifest surface.
│   │   ├── normalize.py                    # Manifest ↔ Commander payload normalization.
│   │   ├── planner.py                      # Plan builder and summary accounting.
│   │   ├── preview.py                      # Preview-key guard (`DSK_PREVIEW=1`).
│   │   ├── redact.py                       # Redaction helpers for plans/diffs/errors.
│   │   ├── rules.py                        # Semantic validation rules beyond JSON schema.
│   │   ├── schema.py                       # JSON-schema loading and validation helpers.
│   │   └── schemas/                        # Packaged JSON schemas.
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
│   │   ├── sandbox.py                      # Ephemeral tenant/scaffold helpers.
│   │   ├── scenarios.py                    # Registered live-smoke scenarios by resource type.
│   │   └── smoke.py                        # End-to-end smoke runner CLI.
│   └── sync_upstream.py                    # Regenerates Commander capability mirror.
└── tests/                                  # Offline/unit/contract coverage.
    ├── __init__.py                         # Tests package marker.
    ├── conftest.py                         # Shared fixtures and test helpers.
    ├── fixtures/                           # Vendored fixture data for clean CI runs.
    │   └── examples/                       # Copied example corpus used by tests.
    ├── test_cli.py                         # CLI command/output/exit-code tests.
    ├── test_commander_cli.py               # Commander provider behavior under mocks.
    ├── test_coverage_followups.py          # Regression coverage for prior review gaps.
    ├── test_diff.py                        # Diff taxonomy tests.
    ├── test_graph.py                       # Graph/order/cycle tests.
    ├── test_h_series_gaps.py               # H-series audit gap regressions.
    ├── test_interfaces.py                  # Protocol/interface conformance tests.
    ├── test_manifest.py                    # Manifest load/dump/canonicalization tests.
    ├── test_metadata.py                    # Marker encode/decode tests.
    ├── test_normalize.py                   # Commander payload normalization tests.
    ├── test_perf.py                        # Performance smoke tests.
    ├── test_planner.py                     # Plan construction/summary tests.
    ├── test_preview_gate.py                # Preview-key guard tests.
    ├── test_providers.py                   # Provider protocol/common-provider tests.
    ├── test_redact.py                      # Redaction contract tests.
    ├── test_rules.py                       # Semantic rule tests.
    ├── test_schema.py                      # Schema and invalid-fixture validation tests.
    ├── test_smoke_scenarios.py             # Offline validation of live-smoke scenario shapes.
    ├── test_stage_5_bindings.py            # `validate --online` stage-5 binding checks.
    └── test_sync_upstream.py               # Capability-mirror generator + `--check` tests.
```

## Where to land new work

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
| 1. Capability parity | `pam_configuration_uid_ref` linking still unresolved/stub-needed | GAP | `V1_GA_CHECKLIST.md`; no dedicated implementation doc/test/file in `keeper_sdk/` |
| 1. Capability parity | Upstream DOR mismatch handled by capability mirror, not the old merge note flow | SHIPPED | `docs/CAPABILITY_MATRIX.md`, `docs/capability-snapshot.json`, `scripts/sync_upstream.py`, `docs/COMMANDER.md` |
| 2. DOR reconciliation | Old “merge NOTES_FROM_SDK upstream” checklist is superseded by shipped mirror/drift model | PARTIAL | `AUDIT.md`, `REVIEW.md`, `docs/COMMANDER.md`, `docs/CAPABILITY_MATRIX.md` |
| 3. CI + release | CI matrix, examples job, drift-check, build wiring are live | SHIPPED | `.github/workflows/ci.yml`, `pyproject.toml` |
| 3. CI + release | First green `main` CI run recorded | SHIPPED | `V1_GA_CHECKLIST.md`, `CHANGELOG.md`, commit `fb6fb8b` in `git log` |
| 3. CI + release | PyPI publish workflow absent | GAP | `.github/workflows/ci.yml` present; no `.github/workflows/publish.yml` in tree |
| 3. CI + release | Signed `v1.0.0` release tag absent | GAP | `git tag -l v1.0.0` returns empty; no release doc/workflow file in tree |
| 4. Login | Built-in env helper + helper contract docs shipped | SHIPPED | `keeper_sdk/auth/helper.py`, `docs/LOGIN.md`, `README.md` |
| 4. Login | Live-smoke explicitly using `EnvLoginHelper` is still missing | GAP | `V1_GA_CHECKLIST.md`; smoke harness lives in `scripts/smoke/` but no committed proof artifact/doc for env-helper path |
| 5. Validate stages | Stage-5 tenant-binding checks implemented + documented | SHIPPED | `keeper_sdk/core/interfaces.py`, `keeper_sdk/providers/commander_cli.py`, `tests/test_stage_5_bindings.py`, `docs/VALIDATION_STAGES.md` |
| 6. Live-smoke coverage | `pamMachine` / `pamDatabase` / `pamDirectory` / `pamRemoteBrowser` scenario registry shipped | SHIPPED | `scripts/smoke/scenarios.py`, `scripts/smoke/smoke.py`, `tests/test_smoke_scenarios.py` |
| 6. Live-smoke coverage | `pamUser` standalone runner not shipped yet | DEFERRED-1.1 | `V1_GA_CHECKLIST.md`, `scripts/smoke/scenarios.py` |
| 6. Live-smoke coverage | Adoption / field-drift / two-writer smokes not shipped yet | DEFERRED-1.1 | `V1_GA_CHECKLIST.md`, `scripts/smoke/scenarios.py` |
| Hardening | DeleteUnsupportedError cleanup already done | SHIPPED | `REVIEW.md`, `keeper_sdk/providers/commander_cli.py` |
| Hardening | `gateway.ksm_application_name` in `reference_existing` still incomplete | GAP | `V1_GA_CHECKLIST.md`, `keeper_sdk/providers/commander_cli.py` |
| Hardening | Renderer snapshots, redact expansion, perf memory assertions still open | GAP | `V1_GA_CHECKLIST.md`, `keeper_sdk/cli/renderer.py`, `keeper_sdk/core/redact.py`, `tests/test_perf.py` |
| Hardening | DOR `TEST_PLAN` scenario mapping + `keeper_sdk` rename are explicitly deferred | DEFERRED-1.1 | `V1_GA_CHECKLIST.md`, `pyproject.toml`, `keeper_sdk/__init__.py` |

## Open questions for next session

- `keeper-pam-declarative` — push to a GitHub remote as the public mirror, or keep local-only? Public makes the drift-check debuggable by third parties; local keeps the marker-wire-format surface unpublished.
- `sdk-live-smoke` branch still carries old `pamform`-era history — rename / delete / leave as snapshot?
- Signed-tag pin for Commander vs the current branch-HEAD pin — does the operator want reproducibility over upstream-tracking?
- `DSK_PREVIEW=1` discoverability — is a one-line check-list in the `validate` error enough, or does it deserve a dedicated doc page?
