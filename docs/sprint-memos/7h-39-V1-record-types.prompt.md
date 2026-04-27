## Sprint 7h-39 V1 — keeper-vault.v1 record_types diff (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/dsk-wt-vault-recordtypes`, branch `cursor/vault-l1-record-types`, base `d76e001`.

# Goal

Extend `compute_vault_diff` in `keeper_sdk/core/vault_diff.py` to detect drift on the `record_types[]` sibling block of `keeper-vault.v1` manifests. Pure offline; no live tenant. Provider apply path is OUT OF SCOPE for this slice (follow-up sprint).

# Required reading

1. `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` — locate `record_types` definition (top-level + `$defs/record_type`).
2. `keeper_sdk/core/vault_models.py:52` — `VaultManifestV1.record_types: list[dict[str, Any]]`.
3. `keeper_sdk/core/vault_diff.py` (88 LOC, full read).
4. `keeper_sdk/core/diff.py` — pattern: `Change`, `ChangeKind`, marker rules (search for `_classify_desired`, `_classify_orphans`).
5. `keeper_sdk/core/interfaces.py` — `LiveRecord` shape (especially `resource_type`, `payload`, `marker`).
6. Existing offline tests: `tests/test_vault_diff.py`.

# Hard requirements

1. Add a new helper `_compute_record_types_changes(manifest, live_record_type_defs)` in `vault_diff.py`. Live record-type defs come in as a separate list of dicts (the discover surface for record types is distinct from records themselves; a future provider patch will populate this; for now it's a parameter).
2. Extend `compute_vault_diff` signature with optional kwarg `live_record_type_defs: list[dict[str, Any]] | None = None`. When non-None, run the new helper and append changes to the returned list.
3. Match key for record types: the type's `$id` field (per `keeper-vault.v1.schema.json` `$defs/record_type` — confirm by reading the schema). Fallback: the `name` field. If both missing, raise `ValueError`.
4. Diff rules:
   - In manifest, not in live → `ChangeKind.ADD`.
   - In live (with marker manager==`keeper-pam-declarative`), not in manifest → `ChangeKind.DELETE` (only when `allow_delete=True`).
   - In both, payloads differ → `ChangeKind.UPDATE`.
   - In live without marker → `ChangeKind.SKIP` with reason `"unmanaged record type"`.
5. NEVER touch marker manager constant.
6. Tests in `tests/test_vault_diff_record_types.py` (NEW; ~12 cases): empty manifest + empty live → no changes; manifest 1, live 0 → 1 ADD; manifest 0, live 1 marker-ours → 1 DELETE; manifest 0, live 1 marker-ours, allow_delete=False → SKIP; manifest 1, live 1 same → no changes; payload field differs → UPDATE; missing $id falls back to name; missing both raises ValueError; live unmanaged → SKIP; collision (two manifest entries same $id) → raises; preserves existing record-level changes alongside record_type changes; manifest_name appears in change rows.
7. Pytest baseline 548+1; expect 548+12 = 560+1.

# Workflow

1. Read all listed files end-to-end.
2. Implement.
3. `python3 -m ruff format keeper_sdk/core/vault_diff.py tests/test_vault_diff_record_types.py && python3 -m ruff check ...`. Fix issues.
4. `python3 -m pytest tests/ -q --no-cov` green.
5. `python3 -m mypy keeper_sdk`. Clean.
6. `git add -A && git commit -m "feat(vault-diff): record_types sibling block (offline)"`.
7. `git push -u origin cursor/vault-l1-record-types`.
8. Output `DONE: cursor/vault-l1-record-types <sha>` or `FAIL: <one-line reason>`.

# Constraints

- Caveman-ultra commit body.
- No live tenant.
- No provider apply implementation.
- Marker manager UNTOUCHED.
- Coordinate with parallel siblings via the kwarg-extension pattern (V2 attachments + V3 keeper_fill add their own kwargs; merge weave on `compute_vault_diff` signature is parent's job, not yours).
