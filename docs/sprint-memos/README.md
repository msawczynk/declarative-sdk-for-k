# Sprint memo archive

This directory keeps the **prompt** + **codex output (or tail)** for every codex worker fired during sprints `7h-37` onward. Future agents can:

- Reuse cite-rich prompt patterns (e.g. how to structure an offline-write slice that won't conflict with parallel siblings).
- Read post-mortem of how a worker self-fixed bugs during a live run (e.g. `7h-38-L1-vault-live.codex-tail.log`).
- Audit the cost/throughput of a sprint by counting workers + reading the final tail lines.

## File naming

- `<sprint>-<slice>-<short-name>.prompt.md` — the prompt the worker received (prompt body, not the env).
- `<sprint>-<slice>-<short-name>.codex.log` — full worker log (kept when small enough; readonly memos).
- `<sprint>-<slice>-<short-name>.codex-tail.log` — last N lines of a large worker log (write workers tend to produce 50k+ line logs because the codex CLI streams the diff in real time).

## What is intentionally NOT archived

- Live-tenant secrets, TOTP, KSM record bodies. The `codex_live.sh` wrapper redacts these before writing the log; the tail snippets here are only the patch-author lines + final result.
- The launch markers (`/tmp/codex-offline-*.marker`) — ephemeral signals, not artifacts.
- The orchestrator's own JOURNAL writes — those live in `JOURNAL.md`.

## How to add a new memo (orchestrator playbook)

After every sprint:

1. `cp /tmp/dsk-<sprint>-<slice>-*.md docs/sprint-memos/<sprint>-<slice>-*.prompt.md` for each worker.
2. For readonly memos (small logs): `cp /tmp/codex-offline-<ts>-*.log docs/sprint-memos/<sprint>-<slice>-*.codex.log`.
3. For write workers (large logs): `tail -200 /tmp/codex-offline-<ts>-*.log > docs/sprint-memos/<sprint>-<slice>-*.codex-tail.log`.
4. For live workers: `tail -400 /tmp/codex-live-<ts>.log > docs/sprint-memos/<sprint>-<slice>-*.codex-tail.log` AND verify no secrets in the tail before commit.
5. `git add docs/sprint-memos/ && git commit -m "docs(sprint-memos): <sprint> archive"`.

## Origin

Established 2026-04-27 in Sprint 7h-39 as part of the codex-utilization optimization review (LESSON `[orchestration][archive-codex-artifacts]`). Retroactively populated for sprints 7h-37 + 7h-38.
