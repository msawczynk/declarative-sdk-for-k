# `scripts/` — orchestration + live smoke

Two sub-trees. `agent/` = parent ↔ Codex orchestration wrappers (offline default,
live-smoke whitelisted). `smoke/` = the live-smoke harness itself.

| Path | Role | Local SCAFFOLD |
|---|---|---|
| `agent/` | Codex CLI wrappers, `phase0_gates.sh`, parallel runner. Logs under `.codex-runs/` (gitignored). | [`agent/SCAFFOLD.md`](./agent/SCAFFOLD.md) |
| `smoke/` | Live-smoke harness. Identity → sandbox → scenario → verify → destroy. Logs under `.smoke-runs/` (gitignored). | [`smoke/SCAFFOLD.md`](./smoke/SCAFFOLD.md) |
| `sync_upstream.py` | Regenerates `docs/capability-snapshot.json`; `--check` mode used by CI `drift-check`. |

## Hard rules

- All scripts are committed. Logs are NOT (`.codex-runs/` and `.smoke-runs/` gitignored).
- Live tenant mutation routes ONLY through `scripts/smoke/smoke.py`. No ad-hoc CLI sessions.
- Codex CLI runs default offline (no network). `codex_live_smoke.sh` is the only network-enabled wrapper, scoped to one whitelisted smoke command.
- `phase0_gates.sh quick` for the inner loop, `full` before merge.

## Reconciliation

`SDK_ORCHESTRATED_FEATURE_COMPLETE.md` Step table maps every gate to a script
in this folder. All shipped.
