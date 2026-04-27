# Daybook harness (from this repo)

**Continuity (JOURNAL / LESSONS) does not live in `declarative-sdk-for-k`.** Canonical
files are on the operator machine (default: `~/Downloads/JOURNAL.md` and
`~/Downloads/LESSONS.md`, synced via the `cursor-daybook` git flow). This folder is
only a **stable entrypoint** so agents run the same scripts from a dsk clone without
vendoring the harness.

**Not a substitute for product live validation.** The SDK’s telling proof against a
real tenant is **live smoke / live pytest** (`scripts/smoke/smoke.py`, `tests/live/`,
env `KEEPER_LIVE_TENANT=1`, evidence + sanitizer). See
[`docs/LIVE_TEST_RUNBOOK.md`](../../docs/LIVE_TEST_RUNBOOK.md) and
[`docs/SDK_DA_COMPLETION_PLAN.md`](../../docs/SDK_DA_COMPLETION_PLAN.md) live-proof
rows. The daybook harness is **agent continuity and merge discipline**; run it in a
separate step from dsk work, and still run live tests when you change provider,
planner, or anything that touches real Commander behavior.

## Commands (from repository root)

| Action | Command |
|--------|---------|
| Session boot (read review + JOURNAL head + cost baseline) | `bash scripts/daybook/harness.sh boot` |
| Pre-claim check (before “done” / support claims) | `bash scripts/daybook/harness.sh pre-claim` |
| Sync canonical daybook to GitHub mirror | `bash scripts/daybook/harness.sh sync` |
| Cost / tier probe | `bash scripts/daybook/harness.sh cost-check` |
| Before Commander / Keeper login | `bash scripts/daybook/harness.sh ksm-preflight` |
| Atomic append (preferred over hand-editing) | `bash scripts/daybook/harness.sh append JOURNAL '…one line…'` |
| After Cursor subagent workers return | `bash scripts/daybook/harness.sh harvest` |
| JOURNAL bloat / distill gate (boot may nag) | `bash scripts/daybook/harness.sh distill-check` |
| End-of-session auto-review digest | `bash scripts/daybook/harness.sh review-loop` |
| Cursor + Codex changelog diff (token-economy triage) | `bash scripts/daybook/harness.sh changelog` |
| Print `export` lines for `~/Downloads` + `DAYBOOK_REPO` | `bash scripts/daybook/harness.sh print-env` |
| Check `DAYBOOK_SYNC_ROOT` (clone present vs wrong `scripts/` path) | `bash scripts/daybook/harness.sh doctor` |

Help: `bash scripts/daybook/harness.sh help`

Implementation: scripts under `~/.cursor-daybook-sync/scripts/`. Set
`DAYBOOK_SYNC_ROOT` to the **clone root** (directory that contains `scripts/`), not
to `.../scripts`. The same path is used as `DAYBOOK_REPO` by `daybook_append` when
you set it alongside `JOURNAL_PATH` / `LESSONS_PATH`.

`daybook_append.sh` defaults `JOURNAL_PATH` / `LESSONS_PATH` to files inside
`~/.cursor-daybook-sync/`. If your **canonical** files live under `~/Downloads/`
(see `AGENT_PREAMBLE.md` / `agent_session_boot.sh`), set before `append` or `sync`:

Or generate the same (with your `$HOME` expanded):

```bash
bash scripts/daybook/harness.sh print-env
# eval:  source <(bash scripts/daybook/harness.sh print-env)
```

Then run `harness.sh append` / `harness.sh sync` in the same shell.

## Troubleshooting

- **`missing directory: .../scripts/scripts` or hint about “clone root”:** you set
  `DAYBOOK_SYNC_ROOT` to the `scripts/` folder. It must be the **parent** of
  `scripts/`. Run `harness.sh doctor` after adjusting `export DAYBOOK_SYNC_ROOT=…`.
- **`daybook_append` wrong file:** set `JOURNAL_PATH` / `LESSONS_PATH` / `DAYBOOK_REPO`
  (see `print-env` above) so append targets `~/Downloads` if that is canonical.

## Discipline: do not mix with dsk product work

- **Do not** add `JOURNAL.md` or `LESSONS.md` to this delivery repo.
- **Do not** run `harness.sh sync` in the same batch as a dsk `git commit` / push of
  product code. Finish or skip one track, then the other.
- **Do** use `append` for JOURNAL/LESSONS lines; if clobber-guard fails, resolve using
  the daybook git repo (see `LESSONS` tag `[daybook][daybook-append-stale-journal]`).

## Phase runner (multi-step workers)

That harness is still workspace-global: `~/.cursor-daybook-sync/scripts/phase_runner.sh`.
In-repo example spec + local gates: `scripts/phase_harness/`.
