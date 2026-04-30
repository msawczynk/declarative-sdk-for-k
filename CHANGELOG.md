# Changelog

All notable changes to `declarative-sdk-for-k` (`dsk`) land here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.3.0] - 2026-04-30

### Added
- feat(mcp): `dsk mcp serve` CLI command starts a stdio JSON-RPC MCP server that exposes manifest tooling to AI agents (gated by optional `mcp` extra).
- feat(pam): `rotation_scripts` field on `pamUser` for declarative `pam rotation script add` attachments, with plan-time warning when readback would require unavailable `pam rotation info --format=json`.
- feat(ksm): `update_app` now wired in `CommanderCliProvider` — KSM app metadata drift triggers an in-place rename instead of delete+recreate.
- feat(diff): `pam_configuration.options` permission-flag drift (connections, tunneling, rotation, remote_browser_isolation, graphical_session_recording, text_session_recording, ai_threat_detection, ai_terminate_session_on_detection) now surfaces as UPDATE rows; previously silently dropped post-import.
- test(live): KSM app lifecycle (token / share / config-output) live-proof accepted against the lab tenant — 3/3 lifecycle ops verified.
- test(live): enterprise teams/roles online-validate live-proof accepted — 18 enterprise objects.
- test(live): `ksm-usage` report live-proof accepted; CLI table + JSON envelope verified end-to-end.
- test(live): KSM bootstrap (`acquire/release/publish/consume`) inter-agent bus live-proof accepted — concurrent-writer CAS verified.

### Changed
- docs(DA plan): KSM bootstrap, KSM bus, ksm-usage, enterprise validate, and KSM lifecycle reclassified to **Live proof ACCEPTED**.
- docs(commander coverage): `update_app` correctly documented as Commander 17.2.16 stable; previous "no update_v5_app" wording corrected.
- docs(scope): `pam_access` (privileged-access) and `pam_tunnel` are operation-only and out of scope for declarative management.
- chore(publish): hardened publish gate scrubs internal-only references from public-facing docs and refuses to push if any reappear.

### Fixed
- fix(diff): `pamConfiguration` permission flags no longer silently ignored — overlay diff against the manifest `options` block (Commander-injected defaults remain unmanaged).

## [2.1.0] - 2026-04-30

### Added
- feat: KSM inter-agent bus CAS protocol (acquire/release/publish/consume + MockBusStore)
- feat: compliance-report graceful empty-cache path (--no-fail-on-empty)
- feat: vault-sharing idempotent re-plan offline coverage
- feat: ksm-usage report Commander-unavailable fallback envelope
- feat: KSM app create SDK wiring (remove CLI gate, wire add_new_v5_app)
- feat: keeper-enterprise.v1 teams/roles additional scaffold tests

### Changed
- chore: repo sanitization (no lab credentials or internal UIDs in public files)

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
