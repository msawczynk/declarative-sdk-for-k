# Daybook — canonical memory for this programme

Long-running work on `declarative-sdk-for-k` is coordinated with a **dedicated
daybook Git repository**, not only in-repo markdown. This file is the **contract**
every **main agent** (orchestrator) and **subagent / worker** on this repo is
expected to follow.

## Canonical store (GitHub)

| Role | Location |
|------|----------|
| **Git repo** | [https://github.com/msawczynk/cursor-daybook](https://github.com/msawczynk/cursor-daybook) |
| **Entry files** | `JOURNAL.md` (state, decisions, open work) · `LESSONS.md` (append-only tagged one-liners) |

On the primary orchestrator machine, `JOURNAL.md` and `LESSONS.md` often live
under `~/Downloads/` as symlinks into a local clone used for sync. Other
machines: clone the repo above or read it on GitHub; do not assume symlinks
exist.

## Sync (mandatory after canonical edits)

Anyone who **commits** changes to canonical `JOURNAL.md` or `LESSONS.md` must
push them through the sync helper (adjust path if your home directory differs):

```bash
/Users/martin/.cursor-daybook-sync/sync_daybook.sh
```

If sync fails (auth, network, merge), report the failure in the session handoff
— do not treat local-only edits as durable team memory.

Orchestrator note: a LaunchAgent may also run this on an interval; manual sync
after substantive edits is still required before closing a session that
changed the daybook.

## Main agent (orchestrator)

The main agent **owns** canonical daybook writes for this programme and the
**sync** step.

1. **Session start:** read `JOURNAL.md` + `LESSONS.md` (canonical), then
   `AGENTS.md` and this file. Re-read after long compaction or worker return.
2. **During work:** follow `.cursor/skills/daybook/SKILL.md` (read → small slice
   → act → parent check → reflect → journal update).
3. **Phase boundary / PR / material decision:** append a session entry to
   `JOURNAL.md`; add one line to `LESSONS.md` only for a **new** durable pattern.
4. **Before handoff:** if `JOURNAL.md` or `LESSONS.md` changed, run
   `sync_daybook.sh` and confirm push succeeded.

Main agent also owns: live-tenant proof design, credential boundaries, GitHub
release safety, gate lifts, and merging support claims with evidence.

## Subagents, Codex workers, Task workers, smoke-only runners

Boot ritual for delegated work lives in:

`/Users/martin/Downloads/.cursor/skills/AGENT_PREAMBLE.md`

**Subset (always):**

- Read canonical `JOURNAL.md` + `LESSONS.md` **silently**; do **not** paste them,
  preamble text, env, secrets, or config dumps into transcripts.
- Stay inside **whitelisted paths** from the task packet. If the task does not
  whitelist daybook files, do **not** edit them — return `LESSON CANDIDATE:` or
  `JOURNAL CANDIDATE:` for the parent to append and sync.
- Run **only** the tests/commands the parent named; report command + PASS/FAIL.
- Do **not** run `sync_daybook.sh` unless the task explicitly whitelists
  daybook writes (normal case: parent syncs).

**Smoke-only / live-harness workers (narrower):**

- Prefer the **inline safety contract** in the harness script (one committed
  command, no secret printing) over dumping preamble/daybook — see
  `LESSONS.md` entries tagged `[token-economy][codex]` for rationale.
- Still return compact DONE + sanitized failure evidence; never claim gate
  lift without parent review of transcript.

## Repo-local vs canonical

- **Canonical:** `cursor-daybook` repo — workspace policy, cross-project
  lessons, orchestration habits.
- **Repo-local:** this repository’s `AGENTS.md`, `docs/SDK_*`, issues — product
  facts and SDK contracts. Prefer canonical daybook for **how we work**;
  prefer repo docs for **what the SDK does**.

## See also

- `AGENTS.md` — CLI, exit codes, guardrails, pointer back here.
- `docs/SDK_COMPLETION_PLAN.md` — roadmap; “done” requires live proof where
  stated.
- `docs/SDK_DA_COMPLETION_PLAN.md` — devil’s-advocate gates and stop rules.
- `.cursor/skills/daybook/SKILL.md` — full daybook discipline reference.
