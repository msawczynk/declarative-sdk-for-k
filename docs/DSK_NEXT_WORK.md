# DSK next work (product orchestration queue)

**Audience:** maintainer or any **credentialed** agent driving **this repo**
(model / role agnostic for live, per `LIVE_TEST_RUNBOOK`). Per-session
coordination, sprint memos, and JOURNAL excerpts stay **out of tree**; see
[`AGENTS.md`](../AGENTS.md) and
`~/.cursor-daybook-sync/docs/orchestration/dsk/`.

**Binding contracts (read before gate lifts):**
[`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md),
[`RECONCILIATION.md`](../RECONCILIATION.md), and
[`docs/SDK_COMPLETION_PLAN.md`](./SDK_COMPLETION_PLAN.md).

**Live access:** any credentialed session following
[`LIVE_TEST_RUNBOOK.md`](./LIVE_TEST_RUNBOOK.md) and `AGENTS.md` may run the
committed live harnesses. The bar is KSM/Commander env in effect, not which
agent implementation is at the wheel.

## Priority stack (post-v1.3.0)

| Focus | What "done" needs | Next command / doc |
|---|---|---|
| **v1.3.0 release baseline** | Local gate is green at 1047 passed / 2 skipped / 1 xfailed. Commander floor is `keepercommander>=17.2.16,<18`, nested `resources[].users[].rotation_settings` is supported, and Phase 7 docs are aligned. | `bash scripts/phase_harness/run_local_gates.sh`; `CHANGELOG.md` |
| **vaultSharingLifecycle live proof** | Second Keeper account sharing create -> clean re-plan -> guarded delete -> cleanup. Offline lifecycle tests are not enough for full mutating support. | `docs/LIVE_TEST_RUNBOOK.md`; `tests/test_vault_shared_folder.py` |
| **Declarative KSM app lifecycle** | Manifest-driven app create -> bind/share -> clean re-plan -> cleanup. `bootstrap-ksm` is supported; general declarative app mutation remains gated. | `docs/SDK_DA_COMPLETION_PLAN.md` Phase 7; `docs/KSM_INTEGRATION.md` |
| **Teams / roles live validate** | Read-only live validate with enterprise scope, then a separate write-design decision before any mutation support claim. | `docs/SDK_DA_COMPLETION_PLAN.md` Phase 7 |
| **Compliance report no-rebuild path** | `dsk report compliance-report --sanitize-uids --quiet` returns a valid redacted JSON envelope without `--rebuild`, or wrapper handling covers Commander empty-cache output. | `docs/SDK_DA_COMPLETION_PLAN.md` Phase 7 |
| **Gateway create / projects / JIT** | Source-backed design + provider conflicts for every unsupported key. Gateway `mode: create`, top-level `projects[]`, and JIT remain v2/upstream-gap work. | `docs/ISSUE_7_GATEWAY_CREATE_PROJECTS_DESIGN.md`; `docs/V2_DECISIONS.md` |
| **KSM inter-agent bus** | Protocol implementation + CAS semantics + live proof. v1.3.0 only ships a sealed API/wire-format stub that raises `CapabilityError` / `NotImplementedError`. | `keeper_sdk/secrets/bus.py`; `docs/KSM_INTEGRATION.md` |
| **Module rename for v2.0.0** | Keep `declarative_sdk_k` shim through v1.x; breaking removal of `keeper_sdk` waits for v2.0.0. | `V1_GA_CHECKLIST.md` |

## Closed / Monitor

| Item | Status | Evidence |
|---|---|---|
| Nested `resources[].users[].rotation_settings` | Supported on Commander 17.2.16+ | `tests/test_pam_rotation_readback.py`; `keeper_sdk/providers/commander_cli.py` |
| Shared-folder Commander write primitives | Supported as command wiring, not full lifecycle | `tests/test_shared_folder_commander.py`; DA Phase 7 |
| KSM bootstrap + `KsmLoginHelper` | Supported | `docs/KSM_BOOTSTRAP.md`; `docs/KSM_INTEGRATION.md` |
| MSP discover / `validate --online` | Supported for MSP admin sessions | `docs/COMMANDER.md` MSP section |
| MSP Commander import / apply | Unsupported | `CommanderCliProvider.apply_msp_plan` raises `CapabilityError` |
| `dsk export`, `dsk diff`, `password-report`, `security-audit-report` | Live-proof accepted | `docs/SDK_DA_COMPLETION_PLAN.md` Current Truth |
| P3 / RBI | Bucketed and smoke-proven for supported rows | [`COMMANDER` § Post-import / RBI](COMMANDER.md#post-import-connection--rbi-tuning-field-map) |

## Every local session (before push)

```bash
bash scripts/phase_harness/run_local_gates.sh
```

Release hygiene:

```bash
python3 -m build
python3 -m twine check dist/*
```

## Multi-step implementation

Use the workspace harness, not a second copy in-tree:

```bash
bash ~/.cursor-daybook-sync/scripts/phase_runner.sh /path/to/phase-spec.yaml
```

Copy-paste starting point + in-repo parent gates:
[`scripts/phase_harness/phase-spec.dsk.example.yaml`](../scripts/phase_harness/phase-spec.dsk.example.yaml).

## Drift

Refresh this queue when `SDK_COMPLETION_PLAN`, `RECONCILIATION`, or `SDK_DA`
changes meaningfully. It is a summarizing index, not a second source of truth.
