# `keeper_sdk/providers/` — backends

Implement `keeper_sdk.core.interfaces.Provider`. Two ship today.

## Modules

| File | LOC | Role |
|---|---:|---|
| `__init__.py` | 6 | Re-exports `MockProvider`, `CommanderCliProvider`. |
| `mock.py` | 207 | Offline in-memory provider. Default for tests + examples CI. Honours markers; emits same outcome shape as live. For **keeper-vault.v1** slice-1, pair with :func:`keeper_sdk.core.vault_diff.compute_vault_diff` + :func:`keeper_sdk.core.vault_graph.vault_record_apply_order` (see `tests/test_vault_mock_provider.py`). |
| `commander_cli.py` | 2402+ | Live provider. Routes through `subprocess` against `keeper` CLI **or** in-process `keepercommander.*` API. **Never** touches `keeper_dag.*` directly. **keeper-vault.v1** slice-1: `discover` filters to `login`; `_apply_vault_plan` uses `RecordAddCommand`, **`RecordEditCommand`** (v3 JSON **UPDATE** + `return_result` guard), `_write_marker`, and `rm`. |
| `_commander_cli_helpers.py` | 407 | Pure module-level helpers extracted out of `commander_cli.py` (D-1 partial split). `_record_from_get`, `_payload_from_get`, `_canonical_payload_from_field`, `_FIELD_LABEL_ALIASES`, `_merge_rbi_dag_options_into_pam_settings`, `_pam_gateway_rows`, `_pam_config_rows`, etc. Heavily unit-tested (`tests/test_commander_cli.py`, `tests/test_rbi_readback.py`). |

## Commander provider — surfaces in use

| Surface | Why | Notes |
|---|---|---|
| `keeper get --format json` | record discovery / verification | walks `fields[]` AND `custom[]` |
| `keeper rm --force` | delete (marker-scoped) | `--force` mandatory; Commander prompts even in batch mode |
| `pam gateway list --format json` | scaffold | JSON contract pinned in `tests/test_coverage_followups.py` |
| `pam config list --format json` | scaffold + stage-5 binding | JSON contract pinned |
| `pam project import` (in-process) | bootstrap | subprocess re-prompts login → forced in-process via `PAMProjectImportCommand` |
| `pam project extend` (in-process) | add resources | same subprocess limitation |
| `pam rotation edit` / `pam rotation list --record-uid` | nested-`pamUser` rotation | supported for `resources[].users[]` on Commander 17.2.16+; top-level/resource rotation stays blocked |
| `record-update` (in-process `record_management.update_record`) | marker writeback | macOS `keeper` 17.1.14 has no `record-update` subcmd; `-cf` syntax fragile across versions |

## In-process API (when subprocess can't auth)

`CommanderCliProvider._run_pam_project_in_process` obtains an authenticated
`KeeperParams` via the configured login helper (`KEEPER_SDK_LOGIN_HELPER` or
the `EnvLoginHelper` env-var fallback) and calls Commander commands directly.
stdout/stderr captured via `contextlib.redirect_stdout` so callers that grep
output (e.g. `access_token=`) keep working.

Floor: `keepercommander>=17.2.16,<18`. Enforced at `apply_plan` start via
`importlib.metadata.version("keepercommander")`. Test:
`tests/test_commander_cli.py::test_apply_rejects_keepercommander_below_minimum`.

## Capability gates

`_detect_unsupported_capabilities` reports unsupported capability hits for:
`rotation_settings`, `default_rotation_schedule`, and `rotation_schedule`.
`apply_plan` raises
`CapabilityError` (with the exact Commander hook in `next_action`) from the
same hits. The gaps also surface as `ChangeKind.CONFLICT` rows in `plan` /
`apply --dry-run` via `Provider.unsupported_capabilities(manifest)`.
Plan = apply parity (C3 fix).

## Vault L1 (`keeper-vault.v1`)

UPDATE path merges ``change.after`` into existing **record version 3** ``data_unencrypted`` (Commander ``RecordEditCommand`` JSON path only supports ``rv == 3``), with ``_vault_merge_custom_for_update`` so manifest ``custom[]`` patches do not drop the SDK ownership marker field. If Commander returns without ``api.update_record_v3``, the provider raises ``CapabilityError`` (stderr tail).

**Caveats / contract (do not duplicate prose here):** [`docs/VAULT_L1_DESIGN.md`](../../docs/VAULT_L1_DESIGN.md) §4 (semantic scalar diff, races), [`docs/VALIDATION_STAGES.md`](../../docs/VALIDATION_STAGES.md) (*Vault — operator caveats*), [`AGENTS.md`](../../AGENTS.md) (vault paragraph after `validate` stages link).

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New provider | new `providers/<name>.py` | `mock.py` (smaller scope) or `commander_cli.py` (full live) |
| New Commander surface call | `commander_cli.py` | `_pam_gateway_rows` flow |
| New pure helper | `_commander_cli_helpers.py` | `_canonical_payload_from_field` |
| New field-label alias | `_commander_cli_helpers.py::_FIELD_LABEL_ALIASES` | `operatingSystem` entry |
| New ignored-drift field (provider-side) | `commander_cli.py::_field_drift` | `pam_configuration_uid_ref` row |

## Hard rules

- **No `keeper_dag.*` writes anywhere.** Project invariant. Tests assert this by mocking `_run_cmd` + `shutil.which`.
- **No real `keeper` CLI invocation in tests.** Mock `_run_cmd`.
- **No secrets in stdout/stderr/log artifacts.** Outcomes use redacted before/after.
- **Subprocess delete must use `--force`.**
- New backends MUST implement: `discover`, `apply_plan`, `unsupported_capabilities`, `check_tenant_bindings`.

## Reconciliation vs design

| Requirement | Status | Where |
|---|---|---|
| Marker writeback after apply | shipped (in-process) | `_write_marker` |
| Per-change verification w/ ignored placement metadata | shipped | `_field_drift` |
| Plan == apply == apply --dry-run capability rows | shipped (C3) | `unsupported_capabilities()` round-trip |
| Stage-5 tenant bindings | shipped | `check_tenant_bindings()` + `tests/test_stage_5_bindings.py` |
| RBI DAG → manifest options merge | shipped (preview-gated until clean re-plan) | `_merge_rbi_dag_options_into_pam_settings` (`tests/test_rbi_readback.py`) |
| Nested-pamUser rotation apply | shipped (preview) | `pam rotation edit` path |
| Nested-pamUser rotation clean re-plan | open (P2.1) | offline diff anchor present; live re-plan parent-verified |
| Top-level `pamUser` | unsupported (v1.1) | `_detect_unsupported_capabilities` |
| Gateway `mode: create` | shipped | `PAMCreateGatewayCommand` in-process path |
| Top-level `projects[]` | preview-gated / design-only | `docs/ISSUE_7_GATEWAY_CREATE_PROJECTS_DESIGN.md` |
| JIT writes via import/extend | shipped | `docs/ISSUE_6_JIT_SUPPORT_BOUNDARY.md` |
