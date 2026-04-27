# `scripts/` — live smoke + capability mirror

| Path | Role | Local SCAFFOLD |
|---|---|---|
| `smoke/` | Live-smoke harness. Identity → sandbox → scenario → verify → destroy. Logs under `.smoke-runs/` (gitignored). | [`smoke/SCAFFOLD.md`](./smoke/SCAFFOLD.md) |
| `sync_upstream.py` | Regenerates `docs/capability-snapshot.json`; `--check` mode used by CI `drift-check`. | – |

## Hard rules

- All scripts are committed. Logs are NOT (`.smoke-runs/` gitignored).
- Live tenant mutation routes ONLY through `scripts/smoke/smoke.py`. No
  ad-hoc CLI sessions.

## Reconciliation

Operator-side tooling is not part of this SDK and is not documented here.
