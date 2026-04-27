## Sprint 7h-39 V3 — keeper-vault.v1 keeper_fill diff (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/dsk-wt-vault-keeperfill`, branch `cursor/vault-l1-keeperfill`, base `d76e001`.

# Goal

Extend `compute_vault_diff` in `keeper_sdk/core/vault_diff.py` to detect drift on the `keeper_fill` (singular, dict) sibling block. Pure offline; no live tenant. Provider apply path is OUT OF SCOPE.

# Required reading

1. `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` — locate `keeper_fill` definition (top-level dict + `$defs/keeper_fill` + `$defs/keeper_fill_setting`).
2. `keeper_sdk/core/vault_models.py:54` — `VaultManifestV1.keeper_fill: dict[str, Any] | None = None`.
3. `keeper_sdk/core/vault_diff.py` (88 LOC).
4. `keeper_sdk/core/diff.py` — `Change`, `ChangeKind`, marker rules.
5. `keeper_sdk/core/interfaces.py` — `LiveRecord` shape.

# Hard requirements

1. `keeper_fill` is SINGULAR (one config per tenant), not a list. The block contains a `settings: list` per `keeper-vault.v1.schema.json $defs/keeper_fill`.
2. Add helper `_compute_keeper_fill_changes(manifest, live_keeper_fill)` in `vault_diff.py`.
3. Extend `compute_vault_diff` with kwarg `live_keeper_fill: dict[str, Any] | None = None`. When non-None, run helper and append changes.
4. Diff rules:
   - Manifest defines `keeper_fill`, live is `None` (or empty dict) → `ChangeKind.ADD` for the whole block (single Change row, uid_ref synthesized as `keeper_fill:tenant`).
   - Live defines `keeper_fill` with marker, manifest sets to `None` → `ChangeKind.DELETE` (only when `allow_delete=True`).
   - Both defined, settings list differs (per-setting match by `domain` field; differing scope/policy → UPDATE) → emit per-setting Change rows.
   - Live `keeper_fill` without marker (i.e., user-managed) → `ChangeKind.SKIP` with reason `"unmanaged keeper_fill"`.
5. Marker placement for `keeper_fill`: the marker is in `live_keeper_fill["marker"]` (or `["custom"]` per existing convention — check `vault_diff.py:34` for marker handling pattern).
6. NEVER touch marker manager constant.
7. Tests in `tests/test_vault_diff_keeper_fill.py` (NEW; ~12 cases): both None → no changes; manifest set, live None → 1 ADD; live set marker-ours, manifest None, allow_delete True → 1 DELETE; same → no changes; settings differ on policy → UPDATE row per affected setting; settings differ on scope → UPDATE; new setting in manifest → ADD setting; removed setting → DELETE setting; live unmanaged → SKIP; manifest_name in rows; preserves record-level changes alongside; collision (two settings same domain in manifest) → ValueError.
8. Pytest baseline 548+1; expect +12.

# Workflow

Same as V1: implement → ruff → pytest → mypy → commit `feat(vault-diff): keeper_fill sibling block (offline)` → push → DONE / FAIL.

# Constraints

- Caveman-ultra commit body.
- No live tenant.
- No provider apply.
- Marker manager UNTOUCHED.
- Parallel sibling slices V1 (record_types) + V2 (attachments); merge weave on `compute_vault_diff` signature is parent's job.
