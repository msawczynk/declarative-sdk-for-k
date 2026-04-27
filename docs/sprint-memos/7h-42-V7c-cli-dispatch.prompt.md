<!-- Generated from templates/SPRINT_offline-write-feature.md, version 2026-04-27 -->

## Sprint 7h-42 V7c — sharing.v1 CLI/manifest dispatch wiring (codex offline write)

Worktree: `/Users/martin/Downloads/Cursor tests/worktrees/cursor-sharing-cli-dispatch`, branch `cursor/sharing-cli-dispatch`, base `674f2b3`.

# Goal

Wire `keeper-vault-sharing.v1` through `load_declarative_manifest` + CLI plan/apply dispatch so `dsk validate sharing.yaml`, `dsk plan sharing.yaml --provider mock`, and `dsk apply sharing.yaml --provider mock` work end-to-end. Out of scope: Commander CLI provider extension (V7b), sibling mock apply (V7a). The wiring lets the existing generic mock provider already round-trip sharing manifests (V6a confirmed); V7c just opens the front door.

# Required reading

1. `keeper_sdk/core/manifest.py` (~150 LOC) — full read. Note `load_manifest` (PAM-only) at line 46, `load_declarative_manifest_string` at line 108 with PAM/VAULT branches at 120/129, error at 133.
2. `keeper_sdk/core/sharing_models.py` (V5a) — `SharingManifestV1`, `load_sharing_manifest`, `SHARING_FAMILY = "keeper-vault-sharing.v1"`.
3. `keeper_sdk/core/sharing_diff.py` (post-V6b) — `compute_sharing_diff(manifest, live_folders=None, live_shared_folders=None, live_share_records=None, live_share_folders=None, ...) -> list[Change]`.
4. `keeper_sdk/cli/main.py` — read:
   - lines 40-70 imports
   - lines 130-160 `validate` command + family branches
   - lines 559-744 `_build_plan` + `plan/apply` commands; note PAM/vault dispatch.
5. `keeper_sdk/core/schema.py` — `SHARING_FAMILY` constant (V5a added or to-be-added; cite); `validate_manifest` family-dispatch.
6. `examples/` directory — find `examples/sharing.example.yaml` (or create one); see `examples/vault.example.yaml` for the shape pattern.
7. LESSON `[capability-census][three-gates]` — V7c closes the CLI dispatch part of provider parity gate.

# Hard requirements

## `keeper_sdk/core/manifest.py` (EDIT)

1. Import `SHARING_FAMILY` and `load_sharing_manifest` from `sharing_models`.
2. In `load_declarative_manifest_string`: add a third branch after the VAULT branch:
   ```python
   if family == SHARING_FAMILY:
       return load_sharing_manifest(document)
   ```
3. Update the error message in the final raise to enumerate all three supported families.
4. Update the module docstring's "PAM + vault L1" caption to "PAM + vault L1 + sharing L1" (or similar). Cite the new family explicitly.

## `keeper_sdk/cli/main.py` (EDIT)

5. Import `SHARING_FAMILY` (or import it from `keeper_sdk.core.schema` / wherever V5a placed it).
6. In `validate` command: add a sharing branch alongside the VAULT branch (lines ~145-160). Sharing-specific validation: just family-validate + typed-load via `load_sharing_manifest`; no graph/online stages yet (those land 7h-43+).
7. In `_build_plan` (lines ~693-744): detect family from the loaded document. When `family == SHARING_FAMILY`, call `compute_sharing_diff(manifest, live_folders=provider.discover_*())` against the provider. Use a NEW helper:
   - `_build_sharing_changes(provider, manifest, *, allow_delete: bool) -> list[Change]` that calls `compute_sharing_diff` with the appropriate `live_*` kwargs sourced from provider state. For mock provider: thread `provider.discover()` through a normalizer that splits records by `resource_type` into the 4 live_* lists. (Cite resource_type strings: `sharing_folder`, `sharing_shared_folder`, `sharing_record_share`, `sharing_share_folder`.)
8. The existing `_make_provider` helper should already work for mock; for commander_cli, V7c does NOT need to wire sharing-specific apply (V7b handles methods, full apply dispatch is 7h-43).

## `examples/sharing.example.yaml` (NEW or VERIFY EXISTS)

9. Minimal manifest: `schema: keeper-vault-sharing.v1`, 1 folder, 1 shared_folder, 1 share_record (user grantee), 1 share_folder (grantee kind="grantee", default_share). Cover all 4 top-level blocks.
10. Add `examples/sharing.example.yaml` to whatever existing schema-coverage CI / examples-validate workflow runs. (Search `.github/workflows/ci.yml` for `examples` jobs — V6c left CI at floor 85.)

## Tests — `tests/test_cli_sharing_dispatch.py` (NEW; ~10 cases)

11. `dsk validate examples/sharing.example.yaml` exits 0; output mentions `keeper-vault-sharing.v1`.
12. `dsk validate <bad-sharing>.yaml` (extra unknown field) exits 1.
13. `dsk plan examples/sharing.example.yaml --provider mock` succeeds; shows N CREATE rows for the 4 blocks.
14. `dsk apply examples/sharing.example.yaml --provider mock --yes` succeeds; round-trips through the generic mock.
15. `dsk plan examples/sharing.example.yaml --provider mock` after apply → 0 actionable changes (clean re-plan).
16. `dsk plan examples/sharing.example.yaml --provider mock --allow-delete` from clean state → 0 changes.
17. Empty manifest after apply → DELETE rows under `--allow-delete`; SKIP rows otherwise.
18. Programmatic `load_declarative_manifest("sharing.yaml")` returns a `SharingManifestV1`.
19. Programmatic `load_manifest("sharing.yaml")` raises (PAM-only entry point per docstring).
20. Schema annotation test: `keeper-vault-sharing.v1.schema.json:x-keeper-live-proof.status` is still `scaffold-only` (will flip to `supported` in 7h-44).

Use `click.testing.CliRunner` for CLI tests; existing tests under `tests/test_cli_*.py` are the pattern reference.

## Tests — `tests/test_manifest_loader_sharing.py` (NEW; ~5 cases)

21. `load_declarative_manifest_string` accepts sharing.v1.
22. `load_declarative_manifest_string` rejects mismatched family with all three names listed in error.
23. `load_manifest_string` (PAM-only) rejects sharing.v1 cleanly.
24. `load_declarative_manifest` reads from disk for a sharing.v1 yaml.
25. Round-trip: load → model_dump → re-load. Idempotent.

## Workflow

1. Read all files end-to-end.
2. Implement manifest.py edits + cli/main.py edits + example yaml + tests.
3. `python3 -m ruff format <files> && python3 -m ruff check keeper_sdk tests`. Fix.
4. Full suite: `python3 -m pytest -q --no-cov`. Baseline 663+1; target +15 → 678+1.
5. `python3 -m pytest -q --cov=keeper_sdk --cov-fail-under=85`. Must stay above 85.
6. `python3 -m mypy <files>`. Clean.
7. `python3 -m keeper_sdk.cli validate examples/sharing.example.yaml` — manual smoke. Must exit 0.
8. `git add -A && git commit -m "feat(sharing-v1): CLI + manifest dispatch wiring (validate/plan/apply via mock)"`.
9. `git push -u origin cursor/sharing-cli-dispatch`.
10. Output `DONE: cursor/sharing-cli-dispatch <sha>` or `FAIL: <one-line>`.

## Constraints

- Caveman-ultra commit body.
- No live tenant.
- Marker manager UNTOUCHED.
- Do not re-add `ChangeKind.ADD`/`SKIP`.
- Do not modify `keeper_sdk/providers/mock.py` (V7a territory).
- Do not modify `keeper_sdk/providers/commander_cli.py` (V7b territory).
- Do not modify `keeper_sdk/core/sharing_diff.py` or `sharing_models.py`.
- Schema status stays `scaffold-only` (the bump waits for live-proof in 7h-44).

# Anti-patterns to avoid (LESSONS-derived)

- LESSON `[orchestration][parallel-write-3way-conflict-pattern]` — strict file boundary; manifest.py + cli/main.py + new test files + new yaml. NOTHING else.
- LESSON `[capability-census][three-gates]` — V7c closes the CLI dispatch portion of gate 2; live-proof gate stays on 7h-44.
- LESSON `[orchestration][2-stage-ratchet]` — if your tests push exact cov below 85, REVERT and DON'T LAND; ask the orchestrator to defer cov bump (already at 85 floor).
- LESSON `[sprint][offline-write-fanout-3way-replication]` — branch from same `674f2b3`; merge zone is manifest.py + cli/main.py only.
