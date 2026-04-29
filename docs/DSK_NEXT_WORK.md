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
| **v1.2.0 shipped baseline** | **2026-04-29 SHIPPED:** current local baseline is **1017 tests / 87% coverage**. Phase 7 is active: shared-folder validate, KSM app `reference_existing`, KSM app create offline bootstrap cases, teams/roles read-only validate, and report command hardening. | `bash scripts/phase_harness/run_local_gates.sh`; `docs/SDK_DA_COMPLETION_PLAN.md` § Phase 7 |
| **Phase 7 in progress — broader Keeper surface** | Keep shared folders, KSM app create, teams/roles, and compliance/security-audit report claims preview-gated until each has upstream-safe write/readback or live read proof. Password-report is already live-proven. | `docs/SDK_DA_COMPLETION_PLAN.md` § Phase 7; `docs/SCAFFOLD.md` test anchors |
| **vaultSharingLifecycle live proof** | **BLOCKED:** needs a second Keeper account before sharing lifecycle can be proven live. Offline coverage is not enough for a mutating support lift. | `docs/LIVE_TEST_RUNBOOK.md`; relevant vault sharing smoke once account exists |
| **Standalone `pamUser`** | **BLOCKED by GH #35:** Commander `pam user ls` ParseError on UID positional arg blocks the safe read path. Do not add more SDK-side workaround code until upstream fixes it. | GitHub **#35**; `DSK_PREVIEW=1` + `DSK_EXPERIMENTAL_ROTATION_APPLY=1` |
| **KSM app create live proof** | Bootstrap sequence is covered offline; next bar is lab proof for create -> bind/share -> clean re-plan -> cleanup. | `docs/SDK_DA_COMPLETION_PLAN.md` § Phase 7; KSM bootstrap/live-smoke docs |
| **Shared folder Commander write modeling** | Phase 7 item: model create/update, memberships, permission diffs, and destructive-change flags before any mutating support claim. | `docs/SDK_DA_COMPLETION_PLAN.md` § Phase 7 |
| **Module rename for v2.0.0** | Rename `keeper_sdk` -> `declarative_sdk_k` with a one-minor compatibility shim for `import keeper_sdk`. Breaking release only. | `V1_GA_CHECKLIST.md` Hardening |
| **Closed / monitor only** | MSP apply live proof passed; P3/RBI evidence is on `main`; KSM bootstrap + `KsmLoginHelper` live passed; `keeper-vault.v1` L1 login CRUD is supported; `dsk export` / `dsk diff` / `dsk report password-report` live proof accepted. | `docs/SDK_DA_COMPLETION_PLAN.md`; `docs/LIVE_TEST_RUNBOOK.md`; [`COMMANDER` § Post-import / RBI](COMMANDER.md#post-import-connection--rbi-tuning-field-map) |

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
