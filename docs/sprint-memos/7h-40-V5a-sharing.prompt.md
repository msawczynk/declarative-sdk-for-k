## Sprint 7h-40 V5a — keeper-vault-sharing.v1 typed models + folders diff (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-v1`, branch `cursor/sharing-v1`, base `306cb26`.

# Goal

Promote `keeper-vault-sharing.v1` from `scaffold-only` to first typed slice: pydantic models for **all 4 top-level blocks** (so subsequent slices extend them) + diff helper for the **`folders[]` block ONLY** + offline tests. Mock provider apply path is OUT OF SCOPE (next sprint slice).

# Required reading

1. `keeper_sdk/core/schemas/keeper-vault-sharing/keeper-vault-sharing.v1.schema.json` — full read (212 LOC). Note 4 top-level blocks: `folders`, `shared_folders`, `share_records`, `share_folders` (oneOf 3 share types). Note `$defs/uid_ref`, `record_ref`, `team_ref`, `sharing_ref` patterns; `$defs/grantee` (user|team); `$defs/record_permissions`; `$defs/folder_grantee_permissions`.
2. `keeper_sdk/core/vault_models.py` (97 LOC) — pattern reference: `_VaultModel` base, `VAULT_FAMILY` const, `VaultManifestV1` top-level, `model_validator` for slice rules, `load_vault_manifest()` family-dispatch entry.
3. `keeper_sdk/core/schema.py` — find `validate_manifest()`, `PAM_FAMILY`, `VAULT_FAMILY` constants. Add a `SHARING_FAMILY = "keeper-vault-sharing.v1"` constant if missing.
4. `keeper_sdk/core/vault_diff.py` — pattern for diff helper structure (now ~640 LOC after 7h-39).
5. `keeper_sdk/core/diff.py:Change`, `ChangeKind` — DO NOT re-add `ChangeKind.ADD` or `ChangeKind.SKIP`; they already exist.
6. `keeper_sdk/core/metadata.py` — `MANAGER_NAME`, `MARKER_VERSION`, `encode_marker`, `MARKER_FIELD_LABEL`, `decode_marker`.
7. Existing offline tests pattern: `tests/test_vault_diff_record_types.py`, `tests/test_vault_diff_attachments.py`, `tests/test_vault_diff_keeper_fill.py`.

# Hard requirements

## Models — `keeper_sdk/core/sharing_models.py` (NEW)

1. Module docstring citing the schema file.
2. `SHARING_FAMILY = "keeper-vault-sharing.v1"`.
3. `_SharingModel` base (pydantic v2 `BaseModel` with `model_config = ConfigDict(populate_by_name=True, extra="forbid")`).
4. Type-faithful pydantic models for all 4 top-level blocks:
   - `SharingFolder` (per `$defs/folder`): `uid_ref: str`, `path: str`, `parent_folder_uid_ref: str | None`, `color: str | None`. Forbid extra keys.
   - `SharingSharedFolder` (per `$defs/shared_folder`): all fields per schema.
   - `SharingRecordShare` (per `$defs/record_share`): all fields per schema.
   - `SharingShareFolder` — discriminated union of `SharedFolderGranteeShare` | `SharedFolderRecordShare` | `SharedFolderDefaultShare`. Use pydantic `Discriminator` or a `model_validator` that dispatches by an explicit discriminator field (READ schema to find the discriminator; if no obvious one, use a custom validator that tries each type).
   - Helper types: `Grantee` (user|team union), `RecordPermissions`, `FolderGranteePermissions`.
5. `SharingManifestV1`:
   - `vault_schema: Literal["keeper-vault-sharing.v1"] = Field(default=SHARING_FAMILY, alias="schema")`.
   - `folders: list[SharingFolder] = Field(default_factory=list)`.
   - `shared_folders: list[SharingSharedFolder] = Field(default_factory=list)`.
   - `share_records: list[SharingRecordShare] = Field(default_factory=list)`.
   - `share_folders: list[SharingShareFolder] = Field(default_factory=list)`.
   - `model_validator(mode="after")` enforces: every `record_ref` in `share_records` and every `sharing_ref` in `folders.parent_folder_uid_ref` references an entry that exists *somewhere* in the manifest OR follows the documented external-reference convention. (Defensive validation; if too strict, narrow.) Cite the schema patterns you enforce.
6. `load_sharing_manifest(document: dict) -> SharingManifestV1`:
   - Family-validate via `validate_manifest()` (you may need to extend `keeper_sdk/core/schema.py` — see below).
   - Raise `SchemaError` if family mismatch.
   - Return `SharingManifestV1.model_validate(document)`.

## Schema dispatch — `keeper_sdk/core/schema.py` (EDIT)

7. Add `SHARING_FAMILY` constant.
8. Extend `validate_manifest()` to accept `keeper-vault-sharing.v1` (cite the existing `if family == VAULT_FAMILY: ...` block and add a peer branch).
9. NEVER touch `PAM_FAMILY` or `VAULT_FAMILY` semantics.

## Diff — `keeper_sdk/core/sharing_diff.py` (NEW; folders block ONLY)

10. Module docstring citing the schema and the slice scope (folders only, other 3 blocks deferred to 7h-41).
11. `_SHARING_FOLDER_RESOURCE = "sharing_folder"`.
12. `_compute_folders_changes(manifest, live_folders, *, manifest_name="vault-sharing", allow_delete=False) -> list[Change]`:
   - Match key: folder `uid_ref` (primary), `path` (secondary fallback).
   - Marker rules: same `MANAGER_NAME` / `manifest` invariants as `vault_diff.py` (cite the patterns).
   - Per-row outcomes:
     - Manifest, not in live → `ChangeKind.ADD`.
     - Both, marker-ours, fields drift → `ChangeKind.UPDATE` (drift on `path`, `parent_folder_uid_ref`, `color`).
     - Both, marker-foreign → `ChangeKind.SKIP` reason `"unmanaged folder"`.
     - Live marker-ours, not in manifest → `ChangeKind.DELETE` (only when `allow_delete=True`); else `SKIP` with `"managed folder missing from manifest; pass --allow-delete to remove"`.
   - Use `Change(... manifest_name=manifest_name)` to keep rows attributable (cite `Change` dataclass for the param).
13. `compute_sharing_diff(manifest, live_folders=None, *, manifest_name="vault-sharing", allow_delete=False) -> list[Change]`:
   - When `live_folders is not None`, dispatch to `_compute_folders_changes`.
   - Future-proof signature with `live_shared_folders`, `live_share_records`, `live_share_folders` kwargs accepted but RAISING `NotImplementedError` if non-None (slice scope enforcement).
14. NEVER touch marker manager constant.

## Tests — `tests/test_sharing_models.py` (NEW; ~10 cases)

15. Empty manifest validates.
16. Manifest with 1 folder validates and round-trips through `model_dump`.
17. Manifest with 1 shared_folder validates.
18. Manifest with 1 record_share validates.
19. Manifest with 1 share_folder of each subtype validates.
20. Schema mismatch → `SchemaError`.
21. Extra unknown top-level key → ValidationError (forbid extra).
22. `parent_folder_uid_ref` malformed pattern → ValidationError.
23. `record_ref` malformed pattern → ValidationError.
24. Grantee with both `user_email` and `team_uid_ref` → ValidationError.

## Tests — `tests/test_sharing_diff_folders.py` (NEW; ~12 cases)

25. Empty manifest + empty live → no changes.
26. Manifest 1 folder, live 0 → 1 ADD.
27. Manifest 0, live 1 marker-ours → 1 DELETE (when `allow_delete=True`).
28. Manifest 0, live 1 marker-ours, `allow_delete=False` → 1 SKIP with reason.
29. Manifest 1, live 1 (same fields) → no changes.
30. `path` drift → UPDATE.
31. `parent_folder_uid_ref` drift → UPDATE.
32. `color` drift → UPDATE.
33. Live unmanaged (marker manager != ours) → SKIP with `"unmanaged folder"`.
34. Two manifest entries with same `uid_ref` → ValueError on diff call.
35. `compute_sharing_diff(manifest, live_shared_folders=[])` raises `NotImplementedError`.
36. `manifest_name` propagates to change rows.

## Workflow

1. Read all listed files end-to-end.
2. Implement.
3. `python3 -m ruff format keeper_sdk/core/sharing_models.py keeper_sdk/core/sharing_diff.py keeper_sdk/core/schema.py tests/test_sharing_models.py tests/test_sharing_diff_folders.py && python3 -m ruff check keeper_sdk tests`. Fix issues.
4. `python3 -m pytest -q --no-cov` green. Baseline 584+1; target +22 → 606+1 (10 model + 12 diff).
5. `python3 -m mypy keeper_sdk/core/sharing_models.py keeper_sdk/core/sharing_diff.py keeper_sdk/core/schema.py tests/test_sharing_models.py tests/test_sharing_diff_folders.py`. Touched files clean.
6. `git add -A && git commit -m "feat(sharing-v1): typed models + folders diff (offline)"`.
7. `git push -u origin cursor/sharing-v1`.
8. Output `DONE: cursor/sharing-v1 <sha>` or `FAIL: <one-line reason>`.

## Constraints

- Caveman-ultra commit body.
- No live tenant.
- No mock provider apply.
- Marker manager UNTOUCHED.
- DO NOT add `ChangeKind` directives — they already exist.
- DO NOT modify other family schemas, models, or diffs.
