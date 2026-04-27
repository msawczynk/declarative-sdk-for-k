<!-- Generated from templates/SPRINT_offline-write-feature.md, version 2026-04-27 -->

## Sprint 7h-41 V6a — sharing.v1 mock provider apply round-trip (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-mock`, branch `cursor/sharing-mock`, base `b30fcbd`.

# Goal

Prove `keeper-vault-sharing.v1` folders block round-trips through the existing `MockProvider`: load manifest → diff → plan → apply → discover → re-diff (clean) → destroy plan → apply destroy → discover (empty). Mock provider is generic over `ChangeKind` so the existing `apply_plan()` SHOULD work without modification — confirm via tests; if a real bug surfaces, fix minimally and document. Out of scope: live tenant; sibling block apply (deferred to 7h-42 once V6b lands sibling diffs).

# Required reading

1. `keeper_sdk/providers/mock.py` (207 LOC) — full read. Note `apply_plan()` dispatches by `ChangeKind.{CREATE,UPDATE,DELETE,CONFLICT}` and is generic over `change.resource_type` + `change.after`. Sharing folder resource type is `"sharing_folder"`.
2. `keeper_sdk/core/sharing_diff.py` (365 LOC) — note `_SHARING_FOLDER_RESOURCE = "sharing_folder"`, `_compute_folders_changes()` emits `Change(resource_type=_SHARING_FOLDER_RESOURCE, ...)` rows.
3. `keeper_sdk/core/sharing_models.py` (229 LOC) — `SharingManifestV1`, `load_sharing_manifest()`.
4. `keeper_sdk/core/planner.py` — `Plan`, `build_plan()`. Find the entry point that takes `list[Change]`.
5. `tests/test_vault_mock_provider.py` — pattern reference for vault round-trip tests through mock.
6. `tests/test_sharing_diff_folders.py` (12 cases, V5a) — reuse fixtures.

# Hard requirements

## Tests — `tests/test_sharing_mock_provider.py` (NEW; ~10 cases)

1. **Empty manifest, empty live → no changes, no apply outcomes.**
2. **CREATE**: 1 folder in manifest, empty mock → apply produces 1 `ApplyOutcome(action="create")`; after apply, `discover()` returns 1 record with `resource_type == "sharing_folder"` and a marker whose `manager == MANAGER_NAME` and `uid_ref` matches the manifest folder.
3. **CREATE then re-diff is clean**: after the create, run `_compute_folders_changes(manifest, live=mock.discover_payloads())` → 0 changes (or N NOOP rows).
4. **UPDATE**: seed mock with a folder marker-ours, manifest has same `uid_ref` but different `path` → diff emits 1 UPDATE → apply succeeds → discover shows new `path`.
5. **DELETE with `allow_delete=True`**: seed mock with folder marker-ours, manifest empty → diff emits 1 DELETE (with allow_delete) → apply succeeds → discover empty.
6. **DELETE refused without `allow_delete`**: same setup, default flag → diff emits 1 SKIP with reason → no apply outcomes for delete (or NOOP).
7. **SKIP unmanaged**: seed mock with a folder whose marker `manager != MANAGER_NAME` → diff emits 1 SKIP with `"unmanaged folder"` → apply produces 0 outcomes for that record.
8. **Round-trip**: 3 folders in manifest, empty mock → CREATE x3, apply, re-diff clean, then manifest emptied + apply destroy + discover empty.
9. **dry_run**: apply with `dry_run=True` → outcomes generated, mock state unchanged. Discover still empty.
10. **Marker propagation**: after CREATE, the marker stored in mock has `MARKER_VERSION` matching `keeper_sdk.core.metadata.MARKER_VERSION` (cite the import).

You will need a small helper that produces `live_folders` payloads from `MockProvider`'s `discover()` (the test-side shape that `_compute_folders_changes` expects). Place it in the test file as `_to_live_folders(records: list[LiveRecord]) -> list[dict]`.

## If a real bug surfaces in `mock.py`

If a test reveals that `MockProvider.apply_plan()` mishandles a sharing-folder Change (e.g. resource_type-specific assumption), patch minimally; add the regression test FIRST. Document the fix in commit message body. DO NOT refactor anything beyond the minimum.

## Workflow

1. Read all listed files end-to-end.
2. Implement tests; iterate `python3 -m pytest -q --no-cov tests/test_sharing_mock_provider.py` until green.
3. `python3 -m ruff format tests/test_sharing_mock_provider.py [any mock.py edits]` then `python3 -m ruff check`.
4. Full suite: `python3 -m pytest -q --no-cov`. Baseline 606+1; target +10 → 616+1.
5. `python3 -m mypy <touched files>`. Clean.
6. `git add -A && git commit -m "feat(sharing-v1): mock provider folders apply round-trip"`.
7. `git push -u origin cursor/sharing-mock`.
8. Output `DONE: cursor/sharing-mock <sha>` or `FAIL: <one-line>`.

## Constraints

- Caveman-ultra commit body.
- No live tenant.
- Marker manager (`keeper-pam-declarative`) UNTOUCHED.
- Do not re-add `ChangeKind.ADD`/`SKIP` (already exist).
- Do not modify other family models/diffs/providers.
- Do not extend `MockProvider` with sharing-specific code unless a real bug forces it; the value is proving generic dispatch suffices.

# Anti-patterns to avoid (LESSONS-derived)

- LESSON `[orchestration][parallel-write-3way-conflict-pattern]` 7h-39 — keep edits scoped to test file + (only-if-required) `mock.py`; do NOT touch `sharing_diff.py` (V6b is editing it in parallel).
- LESSON `[smoke][marker-manager-is-core-contract]` — assert `MANAGER_NAME` round-trips on every CREATE.
- LESSON `[coverage][sealed-skeleton]` — these are real round-trip tests, not stub-coverage gaming.
