# Orchestration — Phase 0 clean + parallel Codex + SDK finish

Canonical **repo-local** contract for `declarative-sdk-for-k`. Global style,
daybook, and drift rules live in user-level Cursor rules + private daybook sync;
this doc is what **forking agents clone** with the repo.

## Roles (token-efficient split)

| Role | Owns | Does not own |
|------|------|----------------|
| **Parent** (primary Cursor / maintainer) | Slice boundaries, prompts, diff review, `phase0_gates.sh` / full CI parity before merge, GitHub push to `main`, live-smoke **approval** (one harness line), gate lifts, support labels, secrets | Bulk offline line edits better delegated |
| **Codex CLI** (`codex exec`) | Scoped offline patches: code + tests + docs in whitelist; focused pytest/ruff on touched paths; DONE block | Broad repo-wide refactors unless scoped; live tenant without whitelisted script |
| **Scripts** | Repeatable gates, smoke wrappers, YAML/shell syntax checks | Product decisions |

**Spend worker tokens on exploration + edits; parent tokens on review, merge, and gates** — aligns with [`docs/CODEX_CLI.md`](./CODEX_CLI.md) and [`docs/SDK_COMPLETION_PLAN.md`](./SDK_COMPLETION_PLAN.md).

## Phase 0 — clean tree (exit criteria)

Source checklist: [`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md) § Phase 0.

1. **Split work** into reviewable PR units (suggested): `.github`/Codex scaffolding; Commander provider; smoke; docs/validation.
2. **Run gates** (non-agentic):

   ```bash
   scripts/agent/phase0_gates.sh quick    # fast loop while iterating
   scripts/agent/phase0_gates.sh full     # before merge / push
   ```

3. **Parent** verifies dirty tree matches PR scope, updates `CHANGELOG.md` for behavior changes, runs devil's-advocate pass from SDK_DA before merge.

## Parallel delivery (features + Codex)

- **One slice = one prompt file** → `scripts/agent/codex_offline_slice.sh path/to/prompt.md` (see [`docs/CODEX_CLI.md`](./CODEX_CLI.md)).
- **Prompt** includes: task, allowed paths, exact test commands, success criteria, no file dumps, DONE contract from [`.github/codex/prompts/scoped-task.md`](../.github/codex/prompts/scoped-task.md).
- **Tracks in parallel** (separate branches/PRs): Phase 1 release hygiene (SDK_DA §1); rotation (§2); RBI/tuning (§3); each obeys **no gate lift without live proof** in SDK_DA.
- **GitHub Codex** (optional): [`docs/CODEX_GITHUB.md`](./CODEX_GITHUB.md) + `.github/workflows/codex-task.yml` for async packets.

## Global optimizations (maintainer machine)

- `python3 ~/.cursor-daybook-sync/scripts/audit_efficiency.py rules-verify` — symlinks + canonical rules.
- Prepend `AGENT_PREAMBLE.md` to every Codex prompt; save long worker stdout to a file; optional `audit_efficiency.py text FILE` on Codex logs.
- **Live smoke:** never background without capturing exit code; use `scripts/agent/codex_live_smoke.sh` or foreground `scripts/smoke/smoke.py` with `tee` if needed.

## Related paths

| Path | Role |
|------|------|
| [`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md) | Devil's-advocate completion contract |
| [`docs/SDK_COMPLETION_PLAN.md`](./SDK_COMPLETION_PLAN.md) | Roadmap + parent loop |
| [`docs/CODEX_CLI.md`](./CODEX_CLI.md) | Codex CLI defaults |
| [`scripts/agent/README.md`](../scripts/agent/README.md) | Wrapper scripts |
| [`AGENTS.md`](../AGENTS.md) | Machine-readable CLI contract |
