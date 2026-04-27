# DSK next work (product orchestration queue)

**Audience:** maintainer or any **credentialed** agent driving **this repo** (model
/ role agnostic for live, per `LIVE_TEST_RUNBOOK`). Per-session
coordination, sprint memos, and JOURNAL excerpts stay **out of tree** — see
[`AGENTS.md`](../AGENTS.md) (where “orchestration” lives) and
`~/.cursor-daybook-sync/docs/orchestration/dsk/`.

**Binding contracts (read before gate lifts):**
[`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md),
[`RECONCILIATION.md`](../RECONCILIATION.md),
[`docs/SDK_COMPLETION_PLAN.md`](./SDK_COMPLETION_PLAN.md).

**Live access (resolve “no access” fallacy):** **any** credentialed session
(follow [`LIVE_TEST_RUNBOOK.md`](./LIVE_TEST_RUNBOOK.md) + [`AGENTS.md`](../AGENTS.md)
**Autonomous execution**) may run the committed live harnesses — not only a
“primary” chat. The bar is **KSM/Commander env in effect**, not which agent
implementation is at the wheel.

## Priority stack (high → lower)

| Focus | What “done” needs | Next command / doc |
|-------|-------------------|-------------------|
| **P3 — `pamRemoteBrowser` / RBI** | Evidence + **COMMANDER P3.1** + **DA §Phase 3** text on `main`. **Next:** close/update GitHub **#5** (maintainer) | [`COMMANDER` § Post-import / RBI](COMMANDER.md#post-import-connection--rbi-tuning-field-map) |
| **P2.1 — nested `pamUser` rotation** | Clean re-plan + destroy on parent-run live smoke | `scripts/smoke/README.md` (`pamUserNestedRotation` / preview flags) |
| **KSM** — bootstrap + `KsmLoginHelper` live | End-to-end live loop in DA table | `pytest` live tests in [`docs/LIVE_TEST_RUNBOOK.md`](./LIVE_TEST_RUNBOOK.md); `tests/live/` |
| **Vault L1, MSP, etc.** | Per DA classification — separate matrix | `SDK_DA` rows; not PAM-bar unless stated |

## Every local session (before push)

```bash
bash scripts/phase_harness/run_local_gates.sh
```

Optional release hygiene: `python3 -m build && python3 -m twine check dist/*` (see
[`docs/SDK_COMPLETION_PLAN.md`](./SDK_COMPLETION_PLAN.md) Current Baseline).

## Multi-step implementation (workers / Codex)

Use the **workspace** harness (YAML spec + gates), **not** a second copy in-tree:

```bash
bash ~/.cursor-daybook-sync/scripts/phase_runner.sh /path/to/phase-spec.yaml
```

Copy-paste starting point + in-repo **parent** gates:
[`scripts/phase_harness/phase-spec.dsk.example.yaml`](../scripts/phase_harness/phase-spec.dsk.example.yaml) — set `repo_root` to your clone.

## Live proof (telling bar)

Unit + offline tests do **not** replace tenant proof for mutating surfaces.
[`docs/LIVE_TEST_RUNBOOK.md`](./LIVE_TEST_RUNBOOK.md). Daybook boot/append is
**continuity** only — [`scripts/daybook/README.md`](../scripts/daybook/README.md).

## Drift

Refresh this queue when `SDK_COMPLETION_PLAN` / `RECONCILIATION` / `SDK_DA` change
meaningfully. It is a **summarizing index**, not a second source of truth.
