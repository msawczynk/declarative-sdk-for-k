## Sprint 7h-37 S2 — vaultOneLogin smoke scenario (codex write-mode)

You are a codex CLI write-mode worker. You are running inside a git worktree at `/Users/martin/Downloads/Cursor tests/dsk-wt-vault-smoke`, branch `cursor/vault-smoke-vaultOneLogin`, branched from `bffa01b` on `main`.

# Goal

Add the `vaultOneLogin` live-smoke scenario per the CDX-4 design memo at `/tmp/dsk-cdx-4-vaultscenario.md` (Path A — separate `VaultScenarioSpec` parallel to `ScenarioSpec`, family-dispatch in `smoke.py`). Land green pytest + offline tests for the new path. NO live tenant calls in this slice — only offline scaffolding + offline tests. The actual live transcript will be captured in Sprint 7h-38 L1.

# Hard requirements

1. **Back-compat:** every existing PAM scenario (pamMachine, pamDatabase, pamDirectory, pamRemoteBrowser, pamUserNested, pamUserNestedRotation) keeps current behavior; their offline tests in `tests/test_smoke_scenarios.py` pass unchanged.
2. **Offline only:** no `keeper` subprocess calls, no live tenant. Add OFFLINE tests for `_vault_one_login_manifest()`, `_verify_vault_one_login()`, and the family-dispatch shim.
3. **Schema validity:** the manifest body produced by `_vault_one_login_manifest()` must `python3 -m json.tool`-validate AND validate against `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` (use `jsonschema`).
4. **Manifest shape:** top-level `schema: keeper-vault.v1`, `records: [...]`. Use ARRAY values for typed fields (`value: ["..."]`) per `keeper-vault.v1.schema.json:120-135`. Include both `Login` label and `Password` label (case `compute_vault_diff` flattens by label per `vault_diff.py:316-335`).
5. **Pytest must stay green** — 517+new passed, 1 skipped baseline.
6. **DO NOT** rely on the multi-profile refactor (S1, parallel sibling slice). Use today's `TITLE_PREFIX` constant. After S1 merges, a 5-LOC follow-up rebase will pick up `--profile`.

# File-by-file change list

### `scripts/smoke/scenarios.py`
- Add at the bottom (after the existing PAM `_SCENARIOS` registry):
  ```python
  @dataclass(frozen=True)
  class VaultScenarioSpec:
      name: str
      family: str  # always "keeper-vault.v1" for this class
      build_manifest: Callable[[str, str], dict[str, Any]]  # (title_prefix, sf_uid) -> full manifest dict
      expected_records: Callable[[str], list[dict]]  # (title_prefix) -> [{"resource_type":"login","title":..,"uid_ref":..}]
      verify: Callable[[Any, Sequence[Any], str], None]  # (manifest_typed, live_records, title_prefix) -> None or raise
      description: str = ""
  ```
- Add `_vault_one_login_manifest(title_prefix: str, sf_uid: str) -> dict[str, Any]` returning the canonical shape:
  ```python
  return {
      "schema": "keeper-vault.v1",
      "records": [
          {
              "uid_ref": f"{title_prefix}-vault-one",
              "type": "login",
              "title": f"{title_prefix}-vault-one",
              "fields": [
                  {"type": "login", "label": "Login", "value": ["smoke@example.invalid"]},
                  {"type": "password", "label": "Password", "value": [_generate_throwaway_password()]},
              ],
          }
      ],
  }
  ```
- Add `_generate_throwaway_password() -> str` returning `secrets.token_urlsafe(16)`.
- Add `_verify_vault_one_login(manifest, live_records, title_prefix)`:
  1. Filter `live_records` to ours (marker manager == `MANAGER_NAME`).
  2. Assert exactly 1 owned record with `(resource_type, title) == ("login", f"{title_prefix}-vault-one")`.
  3. Assert marker `resource_type == "login"`.
  4. Run `compute_vault_diff(manifest, live_records, manifest_name=...)` and assert no `create`/`update`/`conflict` rows.
- Add registry helper `vault_get(name)` and `vault_names()` parallel to existing `get`/`names`.

### `scripts/smoke/smoke.py`
- Argparse: extend `--scenario` choices to include `vaultOneLogin`. Drive choices from `_SCENARIOS.keys() | _VAULT_SCENARIOS.keys()`.
- Family dispatch: at the top of `main()` after parsing args, set `scenario_family` by looking up the name in either registry.
- `_write_manifest()` and `_write_empty_manifest()`: branch by `scenario_family`. For vault, write the full vault doc directly; for PAM, keep the current path.
- `_preflight_manifest()`: for vault, use `load_declarative_manifest()` + `vault_record_apply_order()` + `compute_vault_diff()` per `keeper_sdk/core/manifest.py:88-105` and `vault_diff.py:45-87`. For PAM, keep the current path.
- Verifier section: for vault, skip `_resolve_project_resources_folder()` (vault uses `KEEPER_DECLARATIVE_FOLDER` directly); call `_verify_vault_one_login()` instead of the PAM verifier.
- Destroy: vault empty manifest is `{"schema": "keeper-vault.v1", "records": []}`.

### `tests/test_smoke_vault_scenarios.py` (NEW)
- `test_vault_one_login_manifest_shape`: build manifest, assert top-level keys, assert exactly 1 record with type=login, fields with array values, both Login and Password labels present.
- `test_vault_one_login_manifest_schema_validates`: load schema, validate manifest with `jsonschema.validate`. (Schema family: vault.)
- `test_vault_one_login_manifest_typed_load`: pass through `load_declarative_manifest()` from `keeper_sdk.core.manifest`; expect successful return as `VaultManifestV1`.
- `test_vault_one_login_diff_create_then_clean`:
  - Use a mock provider with empty live records, build manifest, run `compute_vault_diff` — expect 1 ADD.
  - Mock provider apply, then re-run `compute_vault_diff` — expect 0 changes.
- `test_vault_one_login_verifier_pass_and_fail`: build a `LiveRecord` matching the expected shape; call `_verify_vault_one_login()` and assert no raise. Then mutate title; assert raise.
- `test_smoke_argparse_accepts_vault_scenario`: import smoke.py, parse args `["--scenario", "vaultOneLogin"]`, no error; family is `keeper-vault.v1`.

# Workflow

1. Read CDX-4 memo at `/tmp/dsk-cdx-4-vaultscenario.md`.
2. Read each target file end-to-end before editing. Particularly: `scripts/smoke/scenarios.py`, `scripts/smoke/smoke.py`, `keeper_sdk/core/vault_models.py`, `keeper_sdk/core/vault_diff.py`, `keeper_sdk/core/manifest.py`, `keeper_sdk/providers/commander_cli.py:147-250` (vault discover branch).
3. Make edits.
4. Run `python3 -m ruff format scripts/smoke tests/test_smoke_vault_scenarios.py` then `python3 -m ruff check scripts/smoke tests/test_smoke_vault_scenarios.py`. Fix any issues.
5. Run `python3 -m pytest tests/ -q --no-cov` then `python3 -m pytest tests/ -q`. Both green; no regression from baseline 517+1.
6. Run `python3 -m mypy keeper_sdk scripts/smoke`. Clean.
7. `git add -A && git commit -m "feat(smoke): vaultOneLogin scenario (offline scaffolding + tests)" && git push -u origin cursor/vault-smoke-vaultOneLogin`.
8. Output `DONE: cursor/vault-smoke-vaultOneLogin <commit-sha>` or `FAIL: <one-line reason>`.

# Constraints

- Caveman-ultra in commit body.
- No live tenant. No `keeper` subprocess.
- Throwaway password value MUST be generated via `secrets.token_urlsafe()`; never hard-code.
- `compute_vault_diff` is L1; do not assume strong drift detection beyond Login/Password scalars.
- If `keeper-vault.v1` schema rejects the manifest body, fix the manifest, not the schema.
