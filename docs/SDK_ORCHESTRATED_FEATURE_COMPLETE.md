# Orchestrated plan — SDK feature-complete (parent + scripts + workers)

**Authority:** Truthful support beats breadth. When this file disagrees with a
roadmap wish-list, [`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md)
wins.

**Definition of “feature complete”:** Every modeled capability is exactly one of
`supported` | `preview-gated` | `upstream-gap`, with no silent apply/drop, docs
and scaffold aligned, and **live smoke create → verify → clean re-plan →
destroy** for every **supported** mutating path. See SDK_DA “Definition Of Done”.

## Non-negotiable gates (every merge to `main`)

| Step | Command / artifact | Owner |
|------|----------------------|-------|
| Fast loop | `scripts/agent/phase0_gates.sh quick` | Parent or CI |
| Pre-merge | `scripts/agent/phase0_gates.sh full` | Parent |
| Live matrix (optional) | `scripts/agent/run_smoke_matrix.sh` → `.smoke-runs/<ts>/*.log` | Parent |
| Scoped code | `scripts/agent/codex_offline_slice.sh` + prompt from [`.github/codex/prompts/scoped-task.md`](../.github/codex/prompts/scoped-task.md) | Codex CLI (child) |
| Parallel offline slices | `scripts/agent/run_parallel_codex.sh` (disjoint prompts; logs under `.codex-runs/`) | Parent launches, reviews patches |
| Live tenant (whitelisted) | `scripts/agent/codex_live_smoke.sh …` or one explicit `python3 scripts/smoke/smoke.py …` line | Parent approves harness; no secret dumps |
| Optional async | [`docs/CODEX_GITHUB.md`](./CODEX_GITHUB.md) + `.github/workflows/codex-task.yml` | Manual |

**Parent loop (no gate lift without live proof):** delegate narrow edits →
review diff → `quick` → integrate → `full` → one live scenario → classify
(`supported` / `preview-gated` / `upstream-gap`) → update SDK_DA, CHANGELOG,
issues, COMMANDER matrix.

## Phase map (work streams)

| Phase | SDK_DA § | Goal | Offline worker scope | Live proof command (when ready) | Gate to lift |
|-------|----------|------|----------------------|-----------------------------------|----------------|
| 0 | Phase 0 | Clean tree, scripted gates, no false support claims | Docs/scripts/tests only | N/A | Baseline CI green |
| 1 | Phase 1 | GitHub-only release hygiene | `publish.yml`, RELEASING | Install from git/wheel | Release checklist |
| 2 | Phase 2 P2.1 | Nested `rotation_settings` honest | Diff/planner/provider tests; rotation argv helpers | `scripts/smoke/smoke.py --scenario pamUserNestedRotation` (or matrix name in `scenarios.py`) | Re-plan exit 0 + destroy clean; then narrow preview ungate per SDK_DA |
| 3 | Phase 3 P3.x | RBI / post-import tuning readback | `test_rbi_readback.py`, provider enrich | `scripts/smoke/smoke.py --scenario pamRemoteBrowser` | Clean re-plan for fields claimed `edit-supported-clean` in COMMANDER |
| 4 | Phase 4 | Quality: xfails, races, dry-run docs | Unit/integration tests | As needed | Close deferrals with evidence |
| 5 | Phase 5 | JIT boundary | Mirror + docs only unless upstream hook | N/A unless Commander gains writer | Stay `upstream-gap` or prove |
| 6 | Phase 6 | Gateway create / `projects[]` | Design + preview conflicts | Disposable infra proof only | Design doc + explicit support doc |
| 7 | Phase 7 | Broader Keeper surface | Capability mirror extensions | Per-surface smoke | Per-surface DOD |

## Parallel tracks (typical week)

1. **Rotation (P2):** Codex offlines on `tests/test_diff.py`,
   `tests/test_commander_cli.py`, `keeper_sdk/providers/commander_cli.py` —
   parent runs nested rotation smoke once drift cause is classified.
2. **RBI (P3):** Codex offlines on readback helpers + tests; parent runs
   `pamRemoteBrowser` smoke after `discover()` + smoke harness carry manifest and
   session (landed on `main` post e71fb46); **still** needs tenant confirmation
   for TunnelDAG availability.
3. **Release / CI:** Phase 1 tasks without tenant.

## Current honest status (sync with SDK_DA “Current Truth”)

- **GA PAM (non-preview manifests):** supported for core machine/database/dir
  paths with live `pamMachine` proof; matrix entries in `scripts/smoke/README.md`.
- **Nested rotation:** apply path experimental / preview; **re-plan clean** still
  the open gate (SDK_DA P2).
- **RBI:** DAG merge into `pam_settings.options` when in-process session +
  manifest resources exist; smoke passes `manifest_source`; **live** clean
  re-plan remains parent-verified before any “supported” wording on RBI toggles.
- **JIT / gateway create / standalone pamUser:** upstream-gap or preview per
  existing issue/docs — not in this sprint table until design + proof exist.

## Stop conditions

- After **three** failed live attempts on the same blocker: document the exact
  blocker (stderr tail, Commander version, field names), keep `preview-gated`,
  open or update issue — do not speculative-patch (SDK_DA Process Plan).

## Related files

| File | Role |
|------|------|
| [`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md) | Devil's-advocate contract + phase detail |
| [`docs/SDK_COMPLETION_PLAN.md`](./SDK_COMPLETION_PLAN.md) | Long-form roadmap + risk gates |
| [`docs/ORCHESTRATION_PHASE0_PARALLEL.md`](./ORCHESTRATION_PHASE0_PARALLEL.md) | Roles + Phase 0 narrative |
| [`AGENTS.md`](../AGENTS.md) | CLI exit codes + agent playbook |
