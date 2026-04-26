# Orchestrated plan — SDK feature-complete (parent + scripts + workers)

**Authority:** Truthful support beats breadth. When this file disagrees with a
roadmap wish-list, [`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md)
wins.

**Definition of "feature complete":** Every modeled capability is exactly one of
`supported` | `preview-gated` | `upstream-gap`, with no silent apply/drop, docs
and scaffold aligned, and **live smoke create → verify → clean re-plan →
destroy** for every **supported** mutating path. See SDK_DA "Definition Of Done".

## Non-negotiable gates (every merge to `main`)

| Step | Command / artifact | Owner |
|------|----------------------|-------|
| Fast loop | `python3 -m pytest -q tests/test_cli.py tests/test_commander_cli.py tests/test_smoke_scenarios.py tests/test_smoke_args.py` + focused `python3 -m ruff check` on touched paths | Parent or CI |
| Pre-merge | `python3 -m pytest -q && python3 -m ruff check . && python3 -m ruff format --check . && python3 -m mypy keeper_sdk && python3 -m build && python3 -m twine check dist/*` | Parent |
| Live scenario | `python3 scripts/smoke/smoke.py --login-helper env --scenario <name>` (one whitelisted command) | Parent approves; no secret dumps |
| Capability mirror | `python3 scripts/sync_upstream.py --check` (only when capability surface touched) | Parent / CI |

Worker delegation patterns (Codex CLI / cheap subagents / single tight
Cursor turns) and the parent / worker DONE contract are operator-side
infrastructure, maintained canonically in the maintainer's private
daybook (`msawczynk/cursor-daybook`:
`docs/orchestration/` + `templates/`). This repo does not ship the
wrapper scripts or the prompt templates.

**Parent loop (no gate lift without live proof):** delegate narrow edits →
review diff → focused checks → integrate → full pre-merge pass → one
live scenario → classify (`supported` / `preview-gated` / `upstream-gap`)
→ update SDK_DA, CHANGELOG, issues, COMMANDER matrix.

## Phase map (work streams)

| Phase | SDK_DA § | Goal | Offline worker scope | Live proof command (when ready) | Gate to lift |
|-------|----------|------|----------------------|-----------------------------------|----------------|
| 0 | Phase 0 | Clean tree, gates green, no false support claims | Docs/scripts/tests only | N/A | Baseline CI green |
| 1 | Phase 1 | GitHub-only release hygiene | `publish.yml`, RELEASING | Install from git/wheel | Release checklist |
| 2 | Phase 2 P2.1 | Nested `rotation_settings` honest | Diff/planner/provider tests; rotation argv helpers | `python3 scripts/smoke/smoke.py --scenario pamUserNestedRotation` (preview + experimental env) | Re-plan exit 0 + destroy clean; then narrow preview ungate per SDK_DA |
| 3 | Phase 3 P3.x | RBI / post-import tuning readback | `test_rbi_readback.py`, provider enrich | `python3 scripts/smoke/smoke.py --scenario pamRemoteBrowser` | Clean re-plan for fields claimed `edit-supported-clean` in COMMANDER |
| 4 | Phase 4 | Quality: xfails, races, dry-run docs | Unit/integration tests | As needed | Close deferrals with evidence |
| 5 | Phase 5 | JIT boundary | Mirror + docs only unless upstream hook | N/A unless Commander gains writer | Stay `upstream-gap` or prove |
| 6 | Phase 6 | Gateway create / `projects[]` | Design + preview conflicts | Disposable infra proof only | Design doc + explicit support doc |
| 7 | Phase 7 | Broader Keeper surface | Capability mirror extensions | Per-surface smoke | Per-surface DOD |

## Parallel tracks (typical week)

1. **Rotation (P2):** workers offline on `tests/test_diff.py`,
   `tests/test_commander_cli.py`, `keeper_sdk/providers/commander_cli.py` —
   parent runs nested rotation smoke once drift cause is classified.
2. **RBI (P3):** workers offline on readback helpers + tests; parent runs
   `pamRemoteBrowser` smoke after `discover()` + smoke harness carry manifest and
   session (landed on `main` post e71fb46); **still** needs tenant confirmation
   for TunnelDAG availability.
3. **Release / CI:** Phase 1 tasks without tenant.

## Current honest status (sync with SDK_DA "Current Truth")

- **GA PAM (non-preview manifests):** supported for core machine/database/dir
  paths with live `pamMachine` proof; matrix entries in `scripts/smoke/README.md`.
- **Nested rotation:** apply path experimental / preview; **re-plan clean** still
  the open gate (SDK_DA P2).
- **RBI:** DAG merge into `pam_settings.options` when in-process session +
  manifest resources exist; smoke passes `manifest_source`; **live** clean
  re-plan remains parent-verified before any "supported" wording on RBI toggles.
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
| [`AGENTS.md`](../AGENTS.md) | CLI exit codes + agent playbook |
