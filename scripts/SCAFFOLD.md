# `scripts/` — live smoke + capability mirror

| Path | Role | Local SCAFFOLD |
|---|---|---|
| `daybook/` | Forwards to `~/.cursor-daybook-sync` scripts; **no** JOURNAL/LESSONS in the SDK repo. | [README](daybook/README.md) |
| `smoke/` | Live-smoke harness. Identity → sandbox → scenario → verify → destroy. Logs under `.smoke-runs/` (gitignored). | [`smoke/SCAFFOLD.md`](./smoke/SCAFFOLD.md) |
| `phase_harness/` | In-repo `ruff`/`mypy`/`pytest` + example `phase_runner` spec. | [README](phase_harness/README.md) |
| `sync_upstream.py` | Regenerates `docs/capability-snapshot.json`; `--check` mode used by CI `drift-check`. | – |

## Hard rules

- All scripts are committed. Logs are NOT (`.smoke-runs/` gitignored).
- Live tenant mutation routes ONLY through `scripts/smoke/smoke.py`. No
  ad-hoc CLI sessions.

## Reconciliation

Operator-side tooling is not part of this SDK and is not documented here.
