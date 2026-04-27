## Sprint 7h-37 S1 — Multi-profile smoke refactor (codex write-mode)

You are a codex CLI write-mode worker. You are running inside a git worktree at `/Users/martin/Downloads/Cursor tests/dsk-wt-multiprofile`, branch `cursor/smoke-multiprofile`, branched from `bffa01b` on `main`.

# Goal

Land the multi-profile refactor of the SDK live-smoke harness, file-by-file per the prior CDX-1 design memo. The deliverable is a **green-pytest, lint-clean, ruff-formatted, mypy-clean diff** committed to this branch and pushed to `origin/cursor/smoke-multiprofile`. Parent will open the PR — DO NOT open a PR yourself.

# Hard requirements (failure = revert + report)

1. **Back-compat:** `python3 scripts/smoke/smoke.py --scenario pamMachine` (no `--profile` flag) must produce identical behavior to today's main. Add a regression test that pins this.
2. **No live tenant calls in this slice.** Pure offline refactor. The smoke harness is touched, but only in shape; tenant-touching code paths must be byte-identical for `--profile default`.
3. **Marker manager `MANAGER_NAME = "keeper-pam-declarative"` is UNTOUCHED** at `keeper_sdk/core/metadata.py:27`. Profile isolation is by folder/project/title only, never by manager. (See LESSON `[smoke][marker-manager-is-core-contract]` in `/Users/martin/Downloads/LESSONS.md`.)
4. **`dsk plan/apply --node` is OUT OF SCOPE.** Smoke `--node <node_uid>` is metadata only — accept it on the smoke argparse, store in profile context, but DO NOT pass it through to `dsk plan` / `dsk apply` (the SDK CLI lacks the flag at `keeper_sdk/cli/main.py:549-554` and `:647-653`). A docstring comment explains this is deferred.
5. **Pytest must stay green.** Run `python3 -m pytest tests/ -q` at the end. Cov floor is 84% per `.github/workflows/ci.yml:58-64`; do not drop below.

# File-by-file change list

### `scripts/smoke/identity.py`
- Add `@dataclass(frozen=True) class SmokeProfile` with fields:
  - `id: str`
  - `target_email: str`
  - `ksm_config: Path`
  - `admin_commander_config: Path`
  - `sdktest_commander_config: Path`
  - `keeper_server: str = "keepersecurity.com"`
  - `channel_name: str = "sdk-declarative"`  # NOTE: profile suffix appended in `make_default()` etc.
  - `password: str`
  - `default_admin_record_uid: str`
  - `sdk_test_login_record_title: str`
- Define `DEFAULT_PROFILE = SmokeProfile(...)` reproducing today's exact constants from `identity.py:27-39`.
- Add `load_profile(profile_id: str = "default") -> SmokeProfile`:
  1. If `profile_id == "default"` return `DEFAULT_PROFILE`.
  2. Else read `scripts/smoke/profiles/<profile_id>.json` (new directory) — see "Profile JSON shape" below.
  3. If neither file nor `default`, raise `FileNotFoundError` with a clear message pointing at `scripts/smoke/README.md` § "Profiles".
- Make every public function (`admin_login`, `ensure_sdktest_identity`, `_enroll_totp`, `_upsert_admin_record`, `_build_identity_result`, `sdktest_keeper_args`) accept `profile: SmokeProfile | None = None`, defaulting to `DEFAULT_PROFILE` if `None`. Thread the profile field reads through every constant access — no module-level constants used in function bodies for the things now on `SmokeProfile`.
- Add a CLI flag `--profile <id>` to `identity.main()` if it has one; if not, leave alone.

### `scripts/smoke/sandbox.py`
- Add `@dataclass(frozen=True) class SandboxConfig` with fields:
  - `sf_title: str`
  - `ksm_app_name: str`
  - `gateway_name: str`
- Add `def config_for_profile(profile) -> SandboxConfig` returning per-profile suffix-applied names:
  - `default` profile → today's exact constants (`sandbox.py:21-23`).
  - any other profile id `<id>` → `f"SDK Test (ephemeral) {id}"`, `f"SDK Test KSM {id}"`, `"Lab GW Rocky"` (gateway is shared).
- Make every function accept `*, sandbox: SandboxConfig` (or `sandbox=None` defaulting to today's config) and thread through.

### `scripts/smoke/scenarios.py`
- Confirm `ScenarioSpec.build_resources(pam_config_uid_ref, title_prefix)` is unchanged in signature; the only thing that changes is the `title_prefix` value supplied by `smoke.py` (now profile-derived).
- No code changes here unless an existing scenario does NOT honor `title_prefix` — if so, fix it to honor it.

### `scripts/smoke/smoke.py`
- Argparse adds `--profile <id>` (default `default`), `--node <node_uid>` (optional, smoke-side metadata only, NOT forwarded).
- Replace module-level `SMOKE_PROJECT_NAME` / `TITLE_PREFIX` reads with profile-derived values:
  - `SMOKE_PROJECT_NAME = f"sdk-smoke-{profile.id}"` (default profile keeps `sdk-smoke-testuser2` for back-compat — define this rule in `identity.py` `SmokeProfile.project_name` property).
  - `TITLE_PREFIX = f"sdk-smoke-{profile.id}"` (default keeps `sdk-smoke`).
- Construct `CommanderCliProvider(config_file=profile.admin_commander_config, ...)`.
- Pass `sandbox_config` into `sandbox.ensure_sandbox(...)` and `sandbox.teardown_*(...)`.
- Cleanup paths use `MANAGER_NAME` (unchanged).

### `scripts/smoke/profiles/default.example.json` (NEW)
Commit this file (committed; gitignored ARE the per-profile real configs `p1.json`, `p2.json`, etc.). Add `scripts/smoke/profiles/.gitignore` containing `*.json` then `!default.example.json`.

```json
{
  "id": "p1",
  "target_email": "msawczyn+sdk-p1@acme-demo.com",
  "ksm_config": "/Users/martin/Downloads/Cursor tests/keeper-vault-rbi-pam-testenv/ksm-config.json",
  "admin_commander_config": "/Users/martin/Downloads/Cursor tests/keeper-vault-rbi-pam-testenv/commander-config.json",
  "sdktest_commander_config": "scripts/smoke/.commander-config-sdk-p1.json",
  "keeper_server": "keepersecurity.com",
  "channel_name": "sdk-declarative-p1",
  "password": "AcmeDemo123!!",
  "default_admin_record_uid": "MyiZN4cw-wtEIpY1jHlhLw",
  "sdk_test_login_record_title": "SDK Test — sdk-p1 Login"
}
```

### `tests/test_smoke_profile_default_back_compat.py` (NEW)
Pure-Python test (no live tenant). Imports `DEFAULT_PROFILE` and asserts every field matches the historical constant (use the values cited in CDX-1 memo). Imports `config_for_profile(DEFAULT_PROFILE)` and asserts `SandboxConfig.sf_title == "SDK Test (ephemeral)"`, `ksm_app_name == "SDK Test KSM"`, `gateway_name == "Lab GW Rocky"`. Asserts `load_profile()` and `load_profile("default")` both return `DEFAULT_PROFILE`.

### `tests/test_smoke_profile_load.py` (NEW)
- Tests `load_profile("default")` returns `DEFAULT_PROFILE`.
- Tests `load_profile("p1")` reads `scripts/smoke/profiles/p1.json` if present (use `tmp_path` + monkeypatched profile dir).
- Tests `load_profile("does-not-exist")` raises `FileNotFoundError` with a clear message.

### `scripts/smoke/README.md` — append "## Profiles"
Brief section explaining `--profile`, the JSON file shape, and per-profile prerequisites (each profile needs its own test user provisioned; `ensure_sdktest_identity` is profile-aware now). Cite `LESSONS [smoke][marker-manager-is-core-contract]` for why marker isolation is NOT a profile knob.

# Workflow

1. Read CDX-1 memo at `/tmp/dsk-cdx-1-multiprofile.md`. Read `LESSONS.md` for `[smoke][marker-manager-is-core-contract]`.
2. Read each target file end-to-end before editing.
3. Make edits.
4. Run `python3 -m ruff format scripts/smoke tests/test_smoke_profile_*.py` then `python3 -m ruff check scripts/smoke tests/test_smoke_profile_*.py`. Fix any issues.
5. Run `python3 -m pytest tests/ -q --no-cov` then `python3 -m pytest tests/ -q` (with cov). Both must be green; no regressions in count from 517 passed / 1 skipped.
6. Run `python3 -m mypy scripts/smoke keeper_sdk` (or whatever the project mypy invocation is — see `.github/workflows/ci.yml`). Must be clean.
7. `git add -A && git commit -m "feat(smoke): multi-profile refactor (--profile flag, SmokeProfile/SandboxConfig)" && git push -u origin cursor/smoke-multiprofile`.
8. Output a single `DONE: cursor/smoke-multiprofile <commit-sha>` line on success, or `FAIL: <one-line reason>` on failure.

# Constraints

- Caveman-ultra in any commit message body. Bullets, file:line, no marketing.
- Never echo secrets / TOTP / passwords / config blobs.
- If you find yourself wanting to change the marker manager, STOP and exit `FAIL: marker manager is core invariant`.
- If pytest is not green, exit `FAIL: pytest <count> failed` without committing.
