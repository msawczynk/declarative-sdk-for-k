# Changelog

All notable changes to `declarative-sdk-for-k` (`dsk`) land here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial public release scaffolding: `LICENSE` (MIT), `SECURITY.md`, `CHANGELOG.md`.
- GitHub Actions CI: ruff + mypy + pytest on Python 3.11 / 3.12 / 3.13.
- `AGENTS.md` — agent- and LLM-oriented operating manual (exit-code map,
  machine-readable command table, JSON contracts).
- `keeper_sdk.auth` reference login helper (`EnvLoginHelper`) so
  `KEEPER_SDK_LOGIN_HELPER` is now optional for the common case.
- `docs/LOGIN.md` — helper contract + 30-line skeleton for custom flows.
- `V1_GA_CHECKLIST.md` — roadmap toward v1.0.0; now tracks full-K
  scope (vault records, shared folders, teams, roles, enterprise
  config, KSM apps, PAM, compliance, rotation, migration) rather
  than PAM-only.

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
