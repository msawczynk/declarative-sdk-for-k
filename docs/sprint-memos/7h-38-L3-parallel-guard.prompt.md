## Sprint 7h-38 L3 — Concurrency guard implementation (codex offline write-mode)

You are a codex CLI write-mode worker. You are running inside a git worktree at `/Users/martin/Downloads/Cursor tests/dsk-wt-parallel-guard`, branch `cursor/smoke-parallel-guard`, branched from `main` HEAD `91119c4` (after Sprint 7h-37 merge).

# Goal

Implement the `--parallel-profile` concurrency guard for `scripts/smoke/smoke.py` per the design memo. Pure offline; no live tenant. Land green pytest + offline tests for new code paths. Commit + push to `cursor/smoke-parallel-guard`. NO PR — parent merges.

# Required reading

1. **Design memo (authoritative)**: `docs/sprint-memos/7h-37-S3-lock-design.codex.log`. Read top-to-bottom. Implement faithfully.
2. `scripts/smoke/smoke.py` — argparse + main flow + cleanup `finally`.
3. `scripts/smoke/identity.py` — `SmokeProfile`, `DEFAULT_PROFILE`, `load_profile`. The lock embeds `profile_id`, `admin_commander_config`, `sf_title`, `ksm_app_name`, `project_name` from this.
4. `keeper_sdk/auth/helper.py:224-251` — `KEEPER_CONFIG` precedence.
5. `keeper_sdk/providers/commander_cli.py:176-180,1657-1663` — `KEEPER_CONFIG` is honored by Commander invocations.
6. `keeper_sdk/core/metadata.py:27` — marker manager is UNTOUCHED (never per-profile).
7. LESSON `[smoke][marker-manager-is-core-contract]` in `LESSONS.md`.

# Public surface

- New CLI flag on `scripts/smoke/smoke.py`: `--parallel-profile` (boolean, `action="store_true"`).
- Lock dir: `<repo-root>/.dsk-smoke-locks/`. Override via `DSK_SMOKE_LOCK_DIR`.
- `.gitignore` additions: `.dsk-smoke-locks/` near the existing live-smoke/operator artifact block (`.gitignore:22-32`).
- Lock filename: `.dsk-smoke-<tenant_fqdn_safe>-<profile_id>.lock` (sanitize FQDN: replace `.` with `_`).
- Lock file format (JSON): `pid` (int), `started_at` (UTC ISO), `tenant_fqdn` (str), `profile_id` (str), `admin_commander_config` (str absolute physical path), `sf_title` (str), `ksm_app_name` (str), `project_name` (str). NEVER any secrets.

# Refusal conditions (from S3 memo)

Smoke MUST FAIL FAST at preflight if any are true:
1. `--parallel-profile` set but `--profile` is missing or `default` (default profile is shared and unsafe).
2. An active lock with the same physical `admin_commander_config` exists for a different profile.
3. An active lock with the same `sf_title` / `ksm_app_name` / `project_name` exists.
4. The current profile's `admin_commander_config` resolves to the workspace default lab config (`scripts/smoke/identity.py:27-31` constants pre-resolution).
5. `KEEPER_CONFIG` env var is set AND differs from the profile's `admin_commander_config`.

Stale lock recovery:
- PID no longer running → remove + log warning, proceed.
- PID alive but `started_at` > 24h old → refuse with "stuck lock" message.
- Corrupt JSON → refuse, print path, do not guess.

# Tenant identification

- Prefer `admin_params.config["server"]` after admin login.
- Fallbacks: `KEEPER_SERVER` env, `identity.KEEPER_SERVER` constant (`identity.py:33`).
- Sanitize: `tenant_fqdn_safe = re.sub(r"[^A-Za-z0-9-]", "_", tenant_fqdn)`.

# File-by-file changes

### `scripts/smoke/parallel_guard.py` (NEW; ~120 LOC)

Module exporting:
- `LOCK_FILE_VERSION = 1`
- `class GuardError(Exception)` and `class StaleLockError(GuardError)`.
- `@dataclass(frozen=True) class LockInfo`: fields per S3 memo.
- `def lock_dir() -> Path`: returns `Path(os.environ.get("DSK_SMOKE_LOCK_DIR", ROOT / ".dsk-smoke-locks"))` (import `ROOT` from `smoke.py` or duplicate).
- `def list_active_locks() -> list[LockInfo]`: scan dir, parse, filter stale-PID, raise on corrupt JSON.
- `def preflight_check(profile, tenant_fqdn, sandbox_config) -> None`: implements the 5 refusal conditions; raises `GuardError` with a one-line reason.
- `def acquire(profile, tenant_fqdn, sandbox_config, project_name) -> Path`: atomic exclusive create (`open(path, "x")`), write JSON, return lock path.
- `def release(lock_path: Path) -> None`: `path.unlink(missing_ok=True)`; log if missing.

Use `os.kill(pid, 0)` to test PID liveness; on `OSError` PID is dead.

### `scripts/smoke/smoke.py`

- Argparse: add `parser.add_argument("--parallel-profile", action="store_true", help="enable per-profile parallel writer-lane locks; requires --profile != default")`.
- After admin login (after `admin_params` returns from `admin_login`), call `parallel_guard.preflight_check(...)` — but only when `args.parallel_profile` is True. Tenant FQDN: `admin_params.config.get("server") or os.environ.get("KEEPER_SERVER") or identity.KEEPER_SERVER`.
- After preflight passes, call `parallel_guard.acquire(...)` and stash the returned lock path on `state["parallel_lock"]`.
- In `main()`'s outer `finally` (after the existing cleanup), unconditionally call `parallel_guard.release(state.get("parallel_lock"))` if it exists.
- Also register `atexit.register(parallel_guard.release, lock_path)` as best-effort backup.

### `.gitignore`

Add `.dsk-smoke-locks/` near the existing live-smoke/operator artifact block (line 22-32 region).

### `tests/test_smoke_parallel_guard.py` (NEW; ~180 LOC)

Pure-offline. Use `tmp_path` as `DSK_SMOKE_LOCK_DIR` via `monkeypatch.setenv`. Build `SmokeProfile` instances inline (don't load from disk).

Tests:
1. `test_refuses_default_profile`: `--parallel-profile --profile default` → `GuardError` mentioning "default".
2. `test_refuses_default_lab_config`: profile `p1` whose `admin_commander_config` is the default lab path → `GuardError` mentioning "default lab config".
3. `test_refuses_admin_config_collision`: drop a lock with same `admin_commander_config` for profile `p2`; preflight for `p1` matching same path → `GuardError` mentioning "admin_commander_config collision".
4. `test_refuses_resource_collision`: drop a lock with same `sf_title` for profile `p2`; preflight for `p1` matching → `GuardError` mentioning "sf_title".
5. `test_refuses_keeper_config_mismatch`: `KEEPER_CONFIG` set to `/etc/foo`; profile's admin_commander_config is `/etc/bar` → `GuardError` mentioning "KEEPER_CONFIG".
6. `test_acquires_and_releases`: acquire → file exists with right keys; release → file gone.
7. `test_recovers_stale_pid`: drop lock with PID 999999 (assume not running); acquire same profile → lock recreated with current PID, warning logged.
8. `test_refuses_stuck_lock_24h`: drop lock with current PID but `started_at` 25h ago → `StaleLockError` mentioning "stuck".
9. `test_refuses_corrupt_lock`: drop lock with `{"pid":` (invalid JSON) → `GuardError` mentioning "corrupt".
10. `test_atomic_create_collision`: pre-create the lock path; acquire → `GuardError` (rather than overwrite).
11. `test_smoke_argparse_accepts_parallel_profile_flag`: parse `["--scenario","pamMachine","--parallel-profile","--profile","p1"]`; `args.parallel_profile is True`.
12. `test_lock_filename_sanitizes_fqdn`: tenant `keepersecurity.com` → filename contains `keepersecurity_com`.
13. `test_lock_payload_has_no_secrets`: acquire, read lock JSON, assert no field name in {`password`,`totp`,`secret`,`token`,`session`,`config_json`}.

### `scripts/smoke/README.md` — append "## Concurrency / parallel profiles"

Brief: when to use `--parallel-profile`, lock dir location, recovery instructions for stuck locks. Cite `LESSONS [smoke][marker-manager-is-core-contract]` for why marker isolation is NOT a profile knob.

### `docs/live-proof/README.md` — § Concurrency

Find the existing "one live session / writer lane per tenant at a time" block (around line 31-33 / 97-101). Replace with: "one writer per profile per tenant, when profiles use disjoint Commander config paths, test users, shared folders, KSM apps, and project names. The smoke harness enforces this via per-profile lock files when `--parallel-profile` is set; without `--parallel-profile`, the legacy single-writer-per-tenant rule still applies."

# Workflow

1. Read S3 memo at `docs/sprint-memos/7h-37-S3-lock-design.codex.log` end-to-end.
2. Read each target file end-to-end before editing.
3. Implement.
4. `python3 -m ruff format scripts/smoke/parallel_guard.py scripts/smoke/smoke.py tests/test_smoke_parallel_guard.py` then `ruff check ...`. Fix any issues.
5. `python3 -m pytest tests/ -q --no-cov`. Green; baseline 532+1, expect 532+~13 = ~545+1 after this slice.
6. `python3 -m pytest tests/ -q` (with cov). Green. Cov floor 84%.
7. `python3 -m mypy keeper_sdk scripts/smoke`. Clean.
8. `git add -A && git commit -m "feat(smoke): --parallel-profile concurrency guard (lock files; preflight refusal)"`.
9. `git push -u origin cursor/smoke-parallel-guard`.
10. Output `DONE: cursor/smoke-parallel-guard <commit-sha>` or `FAIL: <one-line reason>`.

# Constraints

- Caveman-ultra in commit body.
- No live tenant.
- Marker manager UNTOUCHED.
- Lock JSON contains NO secrets — every test must verify this.
- `os.kill(pid, 0)` is the only PID-liveness check; do NOT shell out to `ps`.
- Lock file is created with exclusive flag (`open(p, "x")`) — must NOT overwrite an existing lock.
