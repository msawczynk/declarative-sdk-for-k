# Codex CLI orchestration (default path)

This repository assumes a **parent orchestrator** (you or your primary Cursor agent) delegates **scoped offline work** to **Codex CLI** (`codex exec`) before doing large edits in-session. GitHub-based Codex (issues, Actions, `@codex`) is for **async / packetized** work when local CLI is unavailable or you want an audit trail on GitHub — see [`docs/CODEX_GITHUB.md`](./CODEX_GITHUB.md).

## Default policy

| Layer | Owns |
|-------|------|
| **Parent** | Issue scope, acceptance criteria, allowed commands, live-smoke command (if any), diff review, full local gate before merge, gate lifts / support labels, secrets, `main`, releases. |
| **Codex CLI worker** | One narrow slice: code + tests + docs inside scope; focused `pytest` / `ruff` on touched paths; returns DONE + file list + commands run. |
| **Live smoke** | Only when parent delegates **one** committed command (e.g. `scripts/agent/codex_live_smoke.sh` or a single `scripts/smoke/smoke.py …` line). Worker must not read credential files or print env/secrets. |

**Spend cheap worker tokens on exploration and edits; spend parent tokens on review, gates, and decisions** — same idea as [`docs/SDK_COMPLETION_PLAN.md`](./SDK_COMPLETION_PLAN.md), with **local `codex exec` as the first choice** for every multi-file or non-trivial patch.

## Prerequisites

- **Codex binary:** on `PATH`, **or** `CODEX_BIN=/path/to/codex`, **or** rely on auto-discovery — `scripts/agent/_codex_resolve.sh` picks the newest `~/.cursor/extensions/openai.chatgpt-*/bin/macos-aarch64/codex` (Cursor ChatGPT extension). `codex_offline_slice.sh` and `codex_live_smoke.sh` call it when `CODEX_BIN` is unset and `codex` is not on `PATH`.
- `CODEX_MODEL` explicitly set (recommended: `gpt-5.5`) so defaults cannot silently downgrade workers.
- Repo root as cwd; worker runs with **workspace-write**, **no network** for offline slices (default in `scripts/agent/codex_offline_slice.sh`).

## Offline worker (no network)

1. Parent writes a **single prompt file** (Markdown or plain text) that includes:
   - Task, scope (paths allowed to touch), success criteria, allowed shell commands.
   - Instruct the worker to end with the DONE block from [`.github/codex/prompts/scoped-task.md`](../.github/codex/prompts/scoped-task.md).
   - Tell the worker **not** to dump large file contents, preamble files, or private notes into the transcript — summary + DONE only.
2. Run:

```bash
export CODEX_MODEL=gpt-5.5
# optional: export CODEX_BIN=/path/to/codex
scripts/agent/codex_offline_slice.sh path/to/your-task-prompt.md
```

3. Parent applies the patch (or merges branch), runs broad checks once per integrated slice (`pytest`, `ruff`, `mypy`, `build` as in `SDK_COMPLETION_PLAN.md`).

## Live smoke worker (network, one command)

Use **`scripts/agent/codex_live_smoke.sh`** only with a parent-approved scenario and harness line. Do not generalise to ad hoc Keeper commands.

## When to use GitHub instead of local CLI

- You want **artifacts** (`codex.patch`, `codex-output.md`) and **manual dispatch** without a local machine — `.github/workflows/codex-task.yml`.
- You want **@codex** on a PR/issue and cloud execution — enable Codex for the repo and use [`docs/CODEX_GITHUB.md`](./CODEX_GITHUB.md).

Local CLI remains the default for **tight inner loops**: faster iteration, same DONE contract, no `OPENAI_API_KEY` secret required on GitHub for local-only work.

## Token efficiency (caveman + wenyan + economy)

- **Parent + Codex + any worker:** same discipline as Cursor primary — **caveman-ultra** on every line the orchestrator or user sees from the worker; **wenyan-ultra** only inside reasoning blocks the product hides from the user (never paste 文言 into chat). See workspace `always-daybook-caveman-ultra.mdc` + `token-economy.mdc`.
- Prepend **`AGENT_PREAMBLE.md`** to offline prompts so workers inherit §3–3b; `scoped-task.md` now names caveman-ultra for the final reply.
- At slice end, worker runs a **short** self-audit (thinking purity + output trim); parent runs the full cadence from `token-economy.mdc` at merge.
- **Heuristic audit (global):** `python3 ~/.cursor-daybook-sync/scripts/audit_efficiency.py text /tmp/codex.out` on saved Codex stdout — same filler/arrow/long-line signals as Cursor transcripts (Cursor meter does not include Codex CLI).

## Anti-patterns

- Hand-editing hundreds of lines in Cursor when Codex could take a scoped prompt with tests.
- Multiple unrelated concerns in one worker prompt — split into 1–3 workers with clear file boundaries.
- Letting any worker remove preview gates or claim `supported` without parent-reviewed live proof.

## Related files

| Path | Role |
|------|------|
| [`docs/ORCHESTRATION_PHASE0_PARALLEL.md`](./ORCHESTRATION_PHASE0_PARALLEL.md) | Phase 0 + parallel tracks; parent vs Codex; **`phase0_gates.sh`** before merge. |
| [`.github/codex/prompts/scoped-task.md`](../.github/codex/prompts/scoped-task.md) | DONE block contract for workers. |
| [`scripts/agent/codex_offline_slice.sh`](../scripts/agent/codex_offline_slice.sh) | Standard offline `codex exec` invocation. |
| [`scripts/agent/codex_live_smoke.sh`](../scripts/agent/codex_live_smoke.sh) | Single-scenario live smoke wrapper. |
| [`scripts/agent/phase0_gates.sh`](../scripts/agent/phase0_gates.sh) | Scripted quick/full gates (non-agentic). |
| [`docs/SDK_COMPLETION_PLAN.md`](./SDK_COMPLETION_PLAN.md) | Parent loop, check budget, Codex rules. |
