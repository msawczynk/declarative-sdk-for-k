# Changelog

All notable changes to `declarative-sdk-for-k` (`dsk`) land here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.0] - 2026-04-30

### Features
- KSM inter-agent bus — CAS-style acquire/release/publish/consume protocol with `MockBusStore` for offline testing
- `dsk report ksm-usage` — `--quiet` flag added; Commander-unavailable fallback envelope
- compliance-report — Graceful empty-cache path (`--no-fail-on-empty`), no longer requires `--rebuild` for the happy path
- KSM app create — CLI gate removed; `CommanderCliProvider` now wires `KSMCommand.add_new_v5_app` with ownership marker write-back
- vault-sharing — Idempotent re-plan offline coverage; live proof accepted (shared_folder_create_count=1 confirmed)
- keeper-enterprise.v1 — Additional teams/roles scaffold tests and fixture

### Quality
- 1375 tests passing (5 skipped, 1 xfailed by design)
- Commander floor: `keepercommander>=17.2.16,<18`
- `workflow_dispatch` trigger added to CI for manual runs

### Repo hygiene
- Public-facing README rewrite, capability status pages
## [2.0.0] - 2026-04-29

### Added
- DSK MCP server over stdio JSON-RPC for lifecycle, report, and KSM bus tools.
- Commander Service Mode provider with async submit, poll, result, FILEDATA, and
  retry handling.
- Expanded schema-family packaging for KSM, enterprise, vault sharing,
  integrations, EPM, and PAM extension foundations.
- Back-compat `declarative_sdk_k` import shim while `keeper_sdk` remains
  supported during the compatibility window.

### Changed
- Package metadata and compatibility shims report `2.0.0`.
- GitHub Actions examples cover plan comments and drift checks.
- Redaction and report paths keep secret values out of JSON output.

## [1.3.0] - 2026-04-29

### Added
- Shared-folder model, mock lifecycle, Commander write primitives, and
  destructive-change guards.
- KSM bootstrap and login-helper integration for credentialed Commander use.
- `msp-environment.v1` schema and read-only Commander validation surface.
- Report wrappers for password, compliance, and security-audit reports.
- Module rename preparation through the `declarative_sdk_k` compatibility shim.

### Changed
- Runtime floor moved to `keepercommander>=17.2.16,<18`.
- Nested PAM user rotation readback is supported on the Commander floor where
  JSON rotation listing is available; unsupported rotation paths remain guarded.
- Vault login L1 compare behavior aligns manifest `fields[]` with
  Commander-flattened scalar values.

## [1.2.0] - 2026-04-29

### Added
- Bundle handoff helper for environments that cannot push directly.
- Vault L1 design, live-proof artifact structure, and declarative loader docs.
- Field-drift, adoption, two-writer, renderer, and performance test coverage.

### Fixed
- PAM plan/diff normalization for partial `pam_settings` overlays.
- Vault Commander update handling for record version 3 JSON edits.
- Session refresh handling around Commander-backed apply and re-plan paths.

## [1.1.0] - 2026-04-26

### Added
- Agent-oriented operating manual, local module scaffolds, and validation stage
  documentation.
- Built-in `EnvLoginHelper` and custom login-helper contract.
- Commander capability mirror, drift snapshot, and validation-stage exit-code
  documentation.
- Example PAM manifests and smoke scenario coverage.

### Changed
- Project renamed to `declarative-sdk-for-k`; primary CLI is `dsk`.
- Legacy `pamform` and `keeper-sdk` CLI aliases remain for backward
  compatibility.
- Runtime metadata requires Python 3.11+.

## [0.y.z] - Pre-release

### Added
- Initial public release scaffolding, MIT license, security policy, CI, and the
  first PAM declarative lifecycle implementation.
