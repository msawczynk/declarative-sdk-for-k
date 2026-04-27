## Sprint 7h-37 S3 — Concurrency-guard design memo (codex readonly)

You are a codex CLI **readonly** worker. Produce a concrete design memo for the `--parallel-profile` concurrency guard that Sprint 7h-38 L3 will implement. NO code changes.

# Required reading

1. CDX-2 concurrency audit memo at `/tmp/dsk-cdx-2-concurrency.md`.
2. `scripts/smoke/smoke.py` argparse + main flow.
3. `keeper_sdk/providers/commander_cli.py:147-250` (vault + PAM discover branches), `:786-806` (vault apply), `:182` and `:1973` (provider session caching).
4. `keeper_sdk/auth/helper.py:224,246` (KEEPER_CONFIG flow).
5. `docs/live-proof/README.md:31-33,97-101` (current "one writer per tenant" rule).
6. LESSONS `[smoke][concurrency]` (CDX-2 candidate, will be added in this sprint's daybook).

# Deliverable shape (~80-120 lines)

```
# Concurrency guard — implementation design (CDX-S3, <UTC ISO>)

## Public surface
- New CLI flag on `scripts/smoke/smoke.py`: `--parallel-profile` (boolean, default false).
- When true, the smoke run records a profile-scoped lock file at:
  `<repo>/.dsk-smoke-<tenant>-<profile_id>.lock`
- Lock file format (JSON, fields):
  - `pid`: int
  - `started_at`: UTC ISO
  - `profile_id`: str
  - `admin_commander_config`: str (path)
  - `sf_title`: str
  - `ksm_app_name`: str
  - `project_name`: str
- Lock release: smoke removes the file in its final teardown / on-exit handler.

## Refusal conditions (smoke must FAIL fast at preflight if any are true)
1. `--parallel-profile` set but `--profile` missing or `default`.
2. Two profile lock files exist with overlapping `admin_commander_config` paths (same physical Commander config = collision risk).
3. Two profile lock files exist with overlapping `sf_title` / `ksm_app_name` / `project_name` (resource collision).
4. The current profile's `admin_commander_config` is the workspace default (`keeper-vault-rbi-pam-testenv/commander-config.json`) AND `--parallel-profile` is set (default config is shared and unsafe).
5. KEEPER_CONFIG env var differs from the profile's `admin_commander_config` (env-vs-profile mismatch, suggests caller bug).

## Tenant identification
- Read `params.config["server"]` after admin login or fall back to `KEEPER_SERVER`. The lock file embeds the tenant FQDN to keep locks per-tenant if the harness is later run against multiple tenants on the same machine.

## Lock-file directory (cited)
- Default: `<repo-root>/.dsk-smoke-locks/`. Add `.gitignore` entry.
- Override via `DSK_SMOKE_LOCK_DIR` env var.

## Failure modes
- Stale lock (PID no longer running): remove + warn, proceed.
- Stale lock (PID alive but file >24h old): refuse + emit "stuck lock" message; require operator to remove.
- Filesystem write fails: refuse + clear message.

## Tests (offline)
- `test_smoke_parallel_guard_refuses_default_profile.py`: runs argparse with `--parallel-profile` + `--profile default`; expect refusal.
- `test_smoke_parallel_guard_detects_config_collision.py`: tmp_path lock dir, drop a fake lock matching admin_commander_config, expect refusal.
- `test_smoke_parallel_guard_releases_on_exit.py`: simulate normal exit, lock file gone.
- `test_smoke_parallel_guard_recovers_stale_pid.py`: drop lock with bogus PID, expect smoke proceeds + warns.

## LOC estimate
- ~100 LOC new code (lock/unlock/check helpers + argparse wiring + on-exit handler).
- ~80 LOC new tests.

## Dependencies
- Multi-profile refactor S1 must be merged FIRST (lock file embeds `profile_id`, `sf_title`, etc.).
- No tenant-side changes.

## Live-proof rule update (paired docs PR)
- `docs/live-proof/README.md` § "Concurrency": replace "one live session / writer lane per tenant at a time" with "one writer per profile per tenant; profiles must use disjoint Commander config paths, test users, shared folders, KSM apps, and project names. The smoke harness enforces this via per-profile lock files when `--parallel-profile` is set."

## CANDIDATE LESSON
- 2026-04-27 [smoke][lock-design] <one line>
```

# Constraints

- Read-only. No code edits.
- Cite file:line for every claim about current state.
- Output the full memo as your final response.
