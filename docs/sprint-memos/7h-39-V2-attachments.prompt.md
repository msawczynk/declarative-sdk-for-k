## Sprint 7h-39 V2 — keeper-vault.v1 attachments diff (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/dsk-wt-vault-attachments`, branch `cursor/vault-l1-attachments`, base `d76e001`.

# Goal

Extend `compute_vault_diff` in `keeper_sdk/core/vault_diff.py` to detect drift on the `attachments[]` sibling block of `keeper-vault.v1` manifests. Pure offline; no live tenant. Provider apply path is OUT OF SCOPE.

# Required reading

1. `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` — locate `attachments` definition (top-level + `$defs/attachment`).
2. `keeper_sdk/core/vault_models.py:53` — `VaultManifestV1.attachments: list[dict[str, Any]]`.
3. `keeper_sdk/core/vault_diff.py` (88 LOC, full read).
4. `keeper_sdk/core/diff.py` — `Change`, `ChangeKind`, marker rules.
5. `keeper_sdk/core/interfaces.py` — `LiveRecord` shape.
6. Existing offline tests: `tests/test_vault_diff.py`.

# Hard requirements

1. Add helper `_compute_attachment_changes(manifest, live_attachments)` in `vault_diff.py`.
2. Extend `compute_vault_diff` with kwarg `live_attachments: list[dict[str, Any]] | None = None`. When non-None, run the helper and append changes.
3. Match key: attachment payload's `record_uid_ref` + `name` (the (record, filename) tuple — confirm shape from schema's `$defs/attachment`). If `record_uid_ref` missing, raise `ValueError`.
4. Diff rules:
   - Manifest entry, not in live → `ChangeKind.ADD`.
   - Live entry (marker manager==`keeper-pam-declarative`), not in manifest → `ChangeKind.DELETE` (only when `allow_delete=True`).
   - Both present, content_hash / size / mime_type differs → `ChangeKind.UPDATE`.
   - Live without marker → `ChangeKind.SKIP` with reason `"unmanaged attachment"`.
5. NEVER touch marker manager constant.
6. Tests in `tests/test_vault_diff_attachments.py` (NEW; ~12 cases): empty/empty → no changes; ADD path; DELETE path with allow_delete True/False; UPDATE on size; UPDATE on hash; UPDATE on mime; missing record_uid_ref → ValueError; collision (same record+name twice in manifest) → ValueError; live unmanaged → SKIP; preserves record-level changes alongside; manifest_name in change rows.
7. Pytest baseline 548+1; expect +12.

# Workflow

Same as V1: implement → ruff → pytest → mypy → commit `feat(vault-diff): attachments sibling block (offline)` → push → DONE / FAIL.

# Constraints

- Caveman-ultra commit body.
- No live tenant.
- No provider apply.
- Marker manager UNTOUCHED.
- Parallel sibling slices V1 (record_types) + V3 (keeper_fill); merge weave on `compute_vault_diff` signature is parent's job.
