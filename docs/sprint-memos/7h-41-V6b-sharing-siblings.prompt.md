<!-- Generated from templates/SPRINT_offline-write-feature.md, version 2026-04-27 -->

## Sprint 7h-41 V6b — sharing.v1 sibling block diffs (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-siblings`, branch `cursor/sharing-siblings`, base `b30fcbd`.

# Goal

Replace the three `NotImplementedError` raises in `keeper_sdk/core/sharing_diff.py:345-350` with real diff helpers for `shared_folders[]`, `share_records[]`, and `share_folders[]`. Wire each through `compute_sharing_diff()` so it returns folders+sibling changes when the corresponding `live_*` argument is provided. ~36 new offline tests across 3 new test modules. Out of scope: mock provider apply for sibling blocks (deferred to 7h-42); live tenant.

# Required reading

1. `keeper_sdk/core/sharing_diff.py` (365 LOC) — full read. Note `_LiveFolder`, `_marker_value`, `_folder_marker`, `_compute_folders_changes` patterns. Replicate the structural pattern PER sibling block.
2. `keeper_sdk/core/sharing_models.py` — `SharingSharedFolder`, `SharingRecordShare`, `SharingShareFolder` (discriminated union of 3 subtypes), `Grantee`, `RecordPermissions`, `FolderGranteePermissions`.
3. `keeper_sdk/core/schemas/keeper-vault-sharing/keeper-vault-sharing.v1.schema.json` — `$defs/shared_folder`, `$defs/record_share`, `$defs/shared_folder_grantee_share`, `$defs/shared_folder_record_share`, `$defs/shared_folder_default_share`. Cite each `$defs` patch you implement against.
4. `keeper_sdk/core/diff.py:Change`, `ChangeKind` — DO NOT add new members. Use existing `CREATE`/`UPDATE`/`DELETE`/`NOOP`/`SKIP`/`CONFLICT`.
5. `keeper_sdk/core/metadata.py` — marker constants and helpers.
6. `keeper_sdk/core/vault_diff.py` — see `_compute_record_types_changes`, `_compute_attachment_changes`, `_compute_keeper_fill_changes` for sibling-block helper structure (introduced in 7h-39 V1/V2/V3). Mirror their conventions.
7. `tests/test_vault_diff_record_types.py`, `tests/test_vault_diff_attachments.py`, `tests/test_vault_diff_keeper_fill.py` — pattern for sibling-block test modules.
8. `tests/test_sharing_diff_folders.py` (V5a) — folders-block test pattern.

# Hard requirements

## Resource types — `keeper_sdk/core/sharing_diff.py` (EDIT)

1. Add module-level constants:
   - `_SHARED_FOLDER_RESOURCE = "sharing_shared_folder"`.
   - `_RECORD_SHARE_RESOURCE = "sharing_record_share"`.
   - `_SHARE_FOLDER_RESOURCE = "sharing_share_folder"`.
2. Add `_*_DIFF_FIELDS` tuples per block listing the fields whose drift triggers UPDATE (read schema to enumerate; e.g. for `shared_folder`: `("name", "default_manage_records", "default_manage_users", "default_can_edit", "default_can_share")`).
3. Define `_LiveSharedFolder`, `_LiveRecordShare`, `_LiveShareFolder` dataclasses mirroring `_LiveFolder`'s shape (frozen, `index`, `raw`, `payload`, `marker`, `keeper_uid`, `uid_ref`, plus block-specific identity fields).

## Diff helpers — `keeper_sdk/core/sharing_diff.py` (EDIT)

4. **`_compute_shared_folders_changes(manifest, live_shared_folders, *, manifest_name="vault-sharing", allow_delete=False) -> list[Change]`**:
   - Match key: `uid_ref` (primary), `name` fallback.
   - Outcomes: ADD (manifest only), UPDATE (drift on `_SHARED_FOLDER_DIFF_FIELDS`), DELETE (live marker-ours not in manifest, allow_delete=True), SKIP (unmanaged or missing-and-not-allowed).
   - Use `Change(resource_type=_SHARED_FOLDER_RESOURCE, manifest_name=manifest_name, ...)`.
5. **`_compute_record_shares_changes(manifest, live_record_shares, *, manifest_name="vault-sharing", allow_delete=False) -> list[Change]`**:
   - Match key: `(record_uid_ref, grantee.user_email | grantee.team_uid_ref)` composite — share rows are scoped by recipient on a record.
   - Outcomes: ADD/UPDATE on permissions drift (`can_edit`, `can_share`), DELETE/SKIP on missing.
6. **`_compute_share_folders_changes(manifest, live_share_folders, *, manifest_name="vault-sharing", allow_delete=False) -> list[Change]`**:
   - Match key: `(shared_folder_uid_ref, kind, grantee_or_record_identifier)`. Three subtypes: grantee_share, record_share, default_share. Default_share has no grantee/record dimension — match by `(shared_folder_uid_ref, "default")`.
   - Outcomes: ADD/UPDATE/DELETE/SKIP per subtype.
7. **Marker rules**: same `MANAGER_NAME` invariants as `_compute_folders_changes`. Raise `OwnershipError` when a managed live row carries a `MARKER_VERSION` higher than supported (cite the existing pattern).

## Wiring — `compute_sharing_diff()` (EDIT lines around 345-350)

8. Replace each `NotImplementedError` raise with a call to the new helper:
   ```python
   if live_shared_folders is not None:
       changes.extend(_compute_shared_folders_changes(manifest, live_shared_folders, manifest_name=manifest_name, allow_delete=allow_delete))
   ```
9. Result order: folders → shared_folders → record_shares → share_folders (deterministic).

## Tests — `tests/test_sharing_diff_shared_folders.py` (NEW; ~12 cases)

10. Empty manifest + empty live → 0 changes.
11. 1 manifest, 0 live → 1 ADD.
12. 0 manifest, 1 live marker-ours, allow_delete=True → 1 DELETE.
13. 0 manifest, 1 live marker-ours, allow_delete=False → 1 SKIP with reason `"managed shared_folder missing from manifest"`.
14. 1 each, no drift → 0 changes (or NOOP).
15. `name` drift → UPDATE.
16. Each `default_*` field drift → UPDATE (parametrize).
17. Live unmanaged → SKIP `"unmanaged shared_folder"`.
18. Two manifest entries with same `uid_ref` → ValueError.
19. `manifest_name` propagates to change rows.
20. Marker version mismatch → `OwnershipError`.
21. Mixed manifest (folders + shared_folders) only emits shared_folder changes when only `live_shared_folders` is passed.

## Tests — `tests/test_sharing_diff_record_shares.py` (NEW; ~12 cases)

22-33. Mirror cases above for record-share semantics. Specifically:
- Match key composite: `(record_uid_ref, grantee.user_email | team_uid_ref)`.
- Permissions drift → UPDATE.
- Same record, different grantee → 2 ADDs.
- Grantee type swap (user→team) → CONFLICT (or DELETE+ADD; pick one and document).

## Tests — `tests/test_sharing_diff_share_folders.py` (NEW; ~12 cases)

34-45. Mirror cases for share_folder discriminated union:
- Each subtype (grantee/record/default) ADD/UPDATE/DELETE/SKIP.
- Default share is unique per shared_folder; two defaults for same folder → ValueError.
- Subtype switch (grantee→record on same shared_folder) → 2 separate rows (different match keys), so ADD + DELETE.

## Workflow

1. Read all listed files end-to-end.
2. Implement helpers + wiring.
3. Implement 3 test modules.
4. `python3 -m ruff format <files>` + `python3 -m ruff check keeper_sdk tests`.
5. `python3 -m pytest -q --no-cov`. Baseline 606+1; target +36 → 642+1.
6. `python3 -m mypy keeper_sdk/core/sharing_diff.py keeper_sdk/core/sharing_models.py tests/test_sharing_diff_*.py`. Clean.
7. `git add -A && git commit -m "feat(sharing-v1): shared_folders + record_shares + share_folders sibling diffs"`.
8. `git push -u origin cursor/sharing-siblings`.
9. Output `DONE: cursor/sharing-siblings <sha>` or `FAIL: <one-line>`.

## Constraints

- Caveman-ultra commit body.
- No live tenant.
- Marker manager UNTOUCHED.
- Do not re-add `ChangeKind.ADD`/`SKIP`.
- Do not modify `keeper_sdk/providers/mock.py` (V6a is touching tests around it in parallel).
- Do not modify other family schemas/models/diffs.
- Do not modify `tests/test_sharing_diff_folders.py` (V5a's existing test file; leave it alone).

# Anti-patterns to avoid (LESSONS-derived)

- LESSON `[orchestration][parallel-write-3way-conflict-pattern]` 7h-39 — your edits to `sharing_diff.py` MUST be additive (add new helpers + new constants below the folders helpers); do NOT refactor existing folders code.
- LESSON `[capability-census][three-gates]` — when a sibling block's diff lands, BUMP the schema's `x-keeper-live-proof.notes` to mention sibling-block diff support is now offline-supported (not just folders). Cite the schema file:line.
- LESSON `[smoke][marker-manager-is-core-contract]` — every helper preserves marker manager invariants.
- LESSON `[sprint][offline-write-fanout-3way-replication]` 7h-40 — V6a is in another worktree on `cursor/sharing-mock`; this slice is `cursor/sharing-siblings`; both branched from same SHA; only `sharing_diff.py` is V6b's domain, only test modules are V6a's domain — keep the boundary clean.
