# Agent scripts — Codex CLI wrappers

Parent orchestration should prefer **Codex CLI** for scoped offline edits. See [`docs/CODEX_CLI.md`](../../docs/CODEX_CLI.md).

| Script | Purpose |
|--------|---------|
| [`phase0_gates.sh`](./phase0_gates.sh) | **Non-agentic** Phase 0 checks: `quick` (focused pytest + ruff + `bash -n` + workflow YAML parse) or `full` (+ full pytest, repo ruff/format, mypy, build + `twine check`). Run before merge; see [`docs/ORCHESTRATION_PHASE0_PARALLEL.md`](../../docs/ORCHESTRATION_PHASE0_PARALLEL.md). |
| [`run_parallel_codex.sh`](./run_parallel_codex.sh) | Run every `scripts/agent/prompts/*.prompt.md` via `codex_offline_slice.sh` in parallel (`MAX_CODEX_JOBS`, default 3); logs under `.codex-runs/` (gitignored). See [`prompts/README.md`](./prompts/README.md). |
| [`_codex_resolve.sh`](./_codex_resolve.sh) | Print resolved Codex path (`CODEX_BIN` → `PATH` → newest Cursor extension bundle). Used by the offline/live wrappers. |
| [`codex_offline_slice.sh`](./codex_offline_slice.sh) | Run `codex exec` with workspace-write sandbox and **no network**; pass a prompt file that includes task, scope, allowed commands, and the DONE contract from `.github/codex/prompts/scoped-task.md`. |
| [`codex_live_smoke.sh`](./codex_live_smoke.sh) | Run **one** whitelisted `scripts/smoke/smoke.py` scenario via Codex with network enabled for the harness only. |
| [`run_smoke_matrix.sh`](./run_smoke_matrix.sh) | **Parent / CI optional:** run all smoke scenarios sequentially with `python3 -u` and per-scenario logs under `.smoke-runs/` (gitignored). Not part of default `phase0_gates` pytest; requires live tenant + lab configs. |

Environment:

- `CODEX_BIN` — path to `codex` if not on `PATH`.
- `CODEX_MODEL` — e.g. `gpt-5.5` (set explicitly in scripts and in parent docs).
- `SMOKE_LOGIN_HELPER` — default `deploy_watcher` for `run_smoke_matrix.sh` (override with `--login-helper`).
