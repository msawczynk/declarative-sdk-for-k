# Daybook harness (from this repo)

**Continuity (JOURNAL / LESSONS) does not live in `declarative-sdk-for-k`.** Canonical
files are on the operator machine (default: `~/Downloads/JOURNAL.md` and
`~/Downloads/LESSONS.md`, synced via the `cursor-daybook` git flow). This folder is
only a **stable entrypoint** so agents run the same scripts from a dsk clone without
vendoring the harness.

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

Help: `bash scripts/daybook/harness.sh help`

Implementation: scripts under `~/.cursor-daybook-sync/scripts/` (override with
`DAYBOOK_SYNC_ROOT` for the **scripts** directory; the clone is also `DAYBOOK_REPO`
for `daybook_append`).

`daybook_append.sh` defaults `JOURNAL_PATH` / `LESSONS_PATH` to files inside
`~/.cursor-daybook-sync/`. If your **canonical** files live under `~/Downloads/`
(see `AGENT_PREAMBLE.md` / `agent_session_boot.sh`), set before `append` or `sync`:

Or generate the same (with your `$HOME` expanded):

```bash
bash scripts/daybook/harness.sh print-env
# eval:  source <(bash scripts/daybook/harness.sh print-env)
```

Then run `harness.sh append` / `harness.sh sync` in the same shell.

## Discipline: do not mix with dsk product work

- **Do not** add `JOURNAL.md` or `LESSONS.md` to this delivery repo.
- **Do not** run `harness.sh sync` in the same batch as a dsk `git commit` / push of
  product code. Finish or skip one track, then the other.
- **Do** use `append` for JOURNAL/LESSONS lines; if clobber-guard fails, resolve using
  the daybook git repo (see `LESSONS` tag `[daybook][daybook-append-stale-journal]`).

## Phase runner (multi-step workers)

That harness is still workspace-global: `~/.cursor-daybook-sync/scripts/phase_runner.sh`.
In-repo example spec + local gates: `scripts/phase_harness/`.
