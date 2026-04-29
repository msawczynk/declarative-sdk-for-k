# Coverage scripts

Offline, informational tooling for SDK coverage denominators.

## Commander command coverage

```bash
python3 scripts/coverage/commander_coverage.py > docs/COMMANDER_COVERAGE.md
```

The extractor reads `docs/COMMANDER.md`, the committed
`docs/capability-snapshot.json` mirror when present, and
`keeper_sdk/providers/commander_cli.py`. It does not import Keeper Commander,
open a Commander session, or call the network.

`docs/COMMANDER_COVERAGE.md` is a manual-refresh artifact, not a CI drift gate.
Refresh it when `docs/COMMANDER.md`, `docs/capability-snapshot.json`, or
`CommanderCliProvider` command wiring changes.
