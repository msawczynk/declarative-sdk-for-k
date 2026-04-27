# 7h-45 V8b — smoke harness vaultSharingLifecycle dispatch

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-harness`, branch `cursor/sharing-harness`, base 8044bb8.

Goal: extend `scripts/smoke/smoke.py` to dispatch the `vaultSharingLifecycle` scenario (which V8a authors in parallel). NO new SPEC, NO new tests.

# Required reading
- `scripts/smoke/smoke.py` full read (~600+ LOC post-7h-37/7h-38 family-dispatch + parallel-guard).
- LESSON `[smoke][family-dispatch-vs-profile-orthogonality]` 7h-37.
- LESSON `[orchestration][parallel-write-3way-conflict-pattern]` 7h-39.

# Hard requirements
1. Find existing `--scenario` argparse choices and `_ACTIVE_SCENARIO_FAMILY` dispatch.
2. Add `"vaultSharingLifecycle"` to argparse choices.
3. In the family-dispatch block, route `keeper-vault-sharing.v1` to the appropriate planner. Use `compute_sharing_diff(manifest, live_folders=..., live_shared_folders=..., live_share_records=..., live_share_folders=...)`. Mock provider's `discover()` returns flat LiveRecord list — split by `resource_type` per V7a's design.
4. Parallel-guard: ensure the scenario acquires a profile lock (existing `parallel_guard` infra from 7h-38 L3).
5. Do NOT modify `scripts/smoke/scenarios.py` (V8a territory).
6. Do NOT add new tests.

# Workflow
1. Read sources.
2. Edit `smoke.py`.
3. ruff format + check.
4. mypy.
5. Full suite green.
6. Manual smoke test commented in commit body: `python -m scripts.smoke.smoke --scenario vaultSharingLifecycle --provider mock --offline` should pass once V8a + V8b are merged together.
7. `git add -A && git commit -m "feat(smoke): vaultSharingLifecycle harness dispatch (7h-45 V8b)"`.
8. `git push -u origin cursor/sharing-harness`.
9. Output `DONE: cursor/sharing-harness <sha>` or `FAIL: <one-line>`.

# Constraints
- ONLY edit `scripts/smoke/smoke.py`.
- Disjoint from V8a (scenarios.py) and V8c (tests/).
- The string `"vaultSharingLifecycle"` is the contract name; V8a creates the SPEC with this exact name.
