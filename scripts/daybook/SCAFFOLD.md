# `scripts/daybook/`

| File | Role |
|------|------|
| [`harness.sh`](harness.sh) | Forwards to `~/.cursor-daybook-sync/scripts` (see [`README.md`](README.md)). |
| [`README.md`](README.md) | Contract: no JOURNAL/LESSONS in the SDK repo; do not mix with dsk `git` commits. |

**Tests:** `tests/test_daybook_harness.py` (help / print-env without a daybook clone).

**Maintainer note:** new stable scripts under `~/.cursor-daybook-sync/scripts/` that
should be invokable from a dsk clone get a subcommand in `harness.sh` + one line in
`print_help` + README table; keep the forwarder list small.
