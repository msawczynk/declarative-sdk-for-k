# `scripts/` — live smoke + capability mirror

| Path | Role | Local SCAFFOLD |
|---|---|---|
| `smoke/` | Live-smoke harness. Identity → sandbox → scenario → verify → destroy. Logs under `.smoke-runs/` (gitignored). | [`smoke/SCAFFOLD.md`](./smoke/SCAFFOLD.md) |
| `sync_upstream.py` | Regenerates `docs/capability-snapshot.json`; `--check` mode used by CI `drift-check`. | – |

## Hard rules

- All scripts are committed. Logs are NOT (`.smoke-runs/` gitignored).
- Live tenant mutation routes ONLY through `scripts/smoke/smoke.py`. No
  ad-hoc CLI sessions.
- Cursor / Codex / daybook orchestration is operator-side infrastructure
  in the maintainer's private daybook (`msawczynk/cursor-daybook`); not
  shipped from this repo.

## Reconciliation

`docs/SDK_ORCHESTRATED_FEATURE_COMPLETE.md` Step table maps every gate to
a script in this folder. All shipped.
