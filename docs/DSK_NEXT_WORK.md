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
| **v1.2.0 shipped baseline** | **2026-04-29 SHIPPED:** `CHANGELOG.md` bumped; local gate baseline is **995 tests / 87% coverage**. Phase 7 entry started: shared-folder validate, KSM app `reference_existing`, renderer snapshots, and perf memory assertion. | `bash scripts/phase_harness/run_local_gates.sh`; `CHANGELOG.md` |
| **Phase 7 continued — broader Keeper surface** | **NEXT:** vault custom fields, multi-record ordering, teams/roles read-only validate, and KSM app create model. Keep every mutating claim preview-gated until there is upstream-safe write/readback, mock/provider coverage, and live clean re-plan proof. | `docs/SDK_DA_COMPLETION_PLAN.md` § Phase 7; `docs/SCAFFOLD.md` test anchors |
| **MSP — `msp-environment.v1` apply** | **2026-04-29 LIVE PROOF:** MSP apply path proven in lab; `validate --online` exit **0** and post-apply plan converged. Import remains unsupported unless explicitly lifted later. | `tests/fixtures/examples/msp/01-minimal-msp.yaml`; `dsk validate --online`; `dsk plan` |
| **GH #35 — nested `pamUser` ParseError** | **OPEN UPSTREAM BLOCKER:** Commander `pam user ls` ParseError on UID positional arg blocks nested `pamUser.rotation_settings` support lift. DSK offline diff work is done; do not chase more SDK code until Commander fixes the read path. | GitHub **#35**; `DSK_PREVIEW=1` + `DSK_EXPERIMENTAL_ROTATION_APPLY=1` |
| **Closed / monitor only** | P3/RBI evidence is on `main` (maintainer close/update GitHub **#5**); KSM bootstrap + `KsmLoginHelper` live passed; `keeper-vault.v1` L1 login CRUD is supported; `dsk export` / `dsk diff` / `dsk report password-report` live proof accepted. | `docs/SDK_DA_COMPLETION_PLAN.md`; `docs/LIVE_TEST_RUNBOOK.md`; [`COMMANDER` § Post-import / RBI](COMMANDER.md#post-import-connection--rbi-tuning-field-map) |

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
