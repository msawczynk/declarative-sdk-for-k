# `scripts/agent/` — Codex CLI orchestration

Parent invokes; Codex (child) executes inside the wrappers. See `README.md`
for the user-facing table; this doc is the **agent-facing** map.

## Files

| File | Role |
|---|---|
| `_codex_resolve.sh` | Print resolved Codex path: `CODEX_BIN` → `PATH` → newest Cursor extension bundle. Sourced by all wrappers. |
| `phase0_gates.sh` | **Non-agentic** Phase-0 checks. `quick` (focused pytest + ruff + `bash -n` + workflow YAML parse). `full` (+ full pytest, repo ruff/format, mypy, build + `twine check`). |
| `codex_offline_slice.sh` | Default offline `codex exec`. Workspace-write sandbox, NO network. Pass a prompt file. Honours `CODEX_MODEL` (set explicitly, e.g. `gpt-5.5`). |
| `codex_live_smoke.sh` | One whitelisted `scripts/smoke/smoke.py` scenario via Codex with network enabled for harness only. Smoke-only workers skip private preamble/orchestration files (token leak guard). |
| `run_parallel_codex.sh` | Run every `prompts/*.prompt.md` through `codex_offline_slice.sh` in parallel (`MAX_CODEX_JOBS`, default 3). Logs under `.codex-runs/<UTC>/`. Skips `00-ping.prompt.md` unless `INCLUDE_PING=1`. |
| `run_smoke_matrix.sh` | Parent / CI optional. Run all smoke scenarios sequentially with `python3 -u`; per-scenario logs in `.smoke-runs/<ts>/`. Requires live tenant + lab configs. |
| `prompts/` | Disjoint slice prompts. `00-ping.prompt.md` (no-edit ping). `01-github-doc.prompt.md`, `02-smoke-docs.prompt.md`, `03-root-docs.prompt.md` (full Codex instruction files w/ task + scope + commands + DONE contract). |
| `prompts/README.md` | How to add a new slice prompt; DONE-block requirement. |
| `README.md` | User-facing wrapper table. |

## Where to land new work

| Change | File / location |
|---|---|
| New Codex slice prompt | `prompts/<NN>-<slug>.prompt.md` (must end with DONE block from `.github/codex/prompts/scoped-task.md`) |
| New non-agentic gate | `phase0_gates.sh` (extend `quick` or `full`) |
| New live-smoke wrapper command | `codex_live_smoke.sh` (whitelist + redaction rules) |
| New parallel-runner knob | `run_parallel_codex.sh` (env var + doc) |

## Hard rules

- Codex CLI runs default offline. Network only via `codex_live_smoke.sh`.
- Smoke-only workers MUST NOT load private orchestration / preamble files (avoid secret/token leak).
- `.codex-runs/` and `.smoke-runs/` MUST stay gitignored.
- DONE contract is mandatory at end of every prompt.
- Parent reviews patches before applying. Codex never auto-pushes to `main`.

## Reconciliation vs design

| Requirement | Status | Evidence |
|---|---|---|
| Default = local Codex CLI offline slice | shipped | `codex_offline_slice.sh`, `docs/CODEX_CLI.md` |
| Phase-0 gates scripted (quick + full) | shipped | `phase0_gates.sh` |
| Parallel disjoint slices | shipped | `run_parallel_codex.sh` + `prompts/` |
| Live-smoke matrix runner | shipped | `run_smoke_matrix.sh` |
| GitHub Actions Codex (optional async) | shipped | `.github/workflows/codex-task.yml` (parent applies patch artifacts locally; never auto-push) |
