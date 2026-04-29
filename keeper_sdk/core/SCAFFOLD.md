# `keeper_sdk/core/` — pure logic

Zero I/O. No subprocess. No Commander imports. Safe to import from anywhere.
This is the contract layer — every behaviour change here ripples into providers + CLI.

## Modules

| File | LOC | Role | Public exports (via `core/__init__.py`) |
|---|---:|---|---|
| `manifest.py` | 176 | Load/dump YAML/JSON manifest; canonicalize. PAM-only vs multi-family loaders (see module docstring). | `load_manifest`, `load_declarative_manifest`, `load_declarative_manifest_string`, `dump_manifest` |
| `schema.py` | 114 | JSON-schema loader + `validate_manifest`. | `load_schema`, `validate_manifest` |
| `models.py` | 469 | Pydantic models for the manifest surface (Manifest, Gateway, PamConfiguration, PamMachine, PamDatabase, PamDirectory, PamRemoteBrowser, PamUser, LoginRecord, Project, SharedFolderBlock, SharedFoldersBlock). `extra="allow"` neither widened nor narrowed. | All resource models |
| `graph.py` | 178 | Build dep DAG + topo `execution_order`; walks `shared_folders`, `projects`, resource `pam_configuration_uid_ref` edges. | `build_graph`, `execution_order` |
| `vault_models.py` | 179 | `keeper-vault.v1` slice-1 Pydantic + `load_vault_manifest`; L1 `login` records plus offline `VaultSharedFolder` / `diff_shared_folder` skeleton. JSON schema + Commander write support for shared folders remain preview-gated. | `VaultManifestV1`, `VaultRecord`, `load_vault_manifest`, `VAULT_MANIFEST_FAMILY` |
| `vault_graph.py` | 87 | Vault dep DAG: duplicate `uid_ref`, `folder_ref` → synthetic prerequisite nodes; `vault_record_apply_order` strips folder nodes. | `build_vault_graph`, `vault_record_apply_order` |
| `vault_diff.py` | 848 | Vault desired-vs-live; field-level match to Commander-flattened scalars. | `compute_vault_diff` |
| `diff.py` | 763 | `compute_diff` PAM: `_index_live` + `_classify_desired` + `_classify_orphans`. Owns `_DIFF_IGNORED_FIELDS`. P2.1 (2026-04-28): `pam_settings.options` treated as overlay (inner keys merged, not wholesale replace); `managed` bool normalized before compare. Nested-`pamUser` `rotation_settings` equality. | `Change`, `ChangeKind`, `compute_diff` |
| `sharing_models.py` | 229 | `keeper-vault-sharing.v1` Pydantic + loaders; `SharingSharedFolder` models `shared_folders[]` (P21 landed). | Sharing manifest types |
| `sharing_diff.py` | 1300 | Sharing desired-vs-live; large single file — see LESSONS threshold-driven split decision before fan-out refactors. | `compute_sharing_diff` (export name per `__init__`) |
| `msp_models.py` | 110 | `msp-environment.v1` Pydantic + load helper. | MSP manifest types |
| `msp_graph.py` | 63 | MSP dep graph / ordering. | `build_msp_graph`, `msp_apply_order` |
| `msp_diff.py` | 287 | MSP discover vs manifest (`compute_msp_diff`). Commander **apply/import** for MSP stay unsupported — `AGENTS.md` matrix. | `compute_msp_diff` |
| `planner.py` | 90 | Build `Plan` from changes; summary accounting (create/update/delete/conflict/noop). | `Plan`, `build_plan` |
| `interfaces.py` | 125 | Typed protocols: `Provider`, `MetadataStore`, `Renderer`, `LiveRecord`, `ApplyOutcome`. Provider exposes `discover()`, `apply_plan()`, `unsupported_capabilities()`, `check_tenant_bindings()`. | `Provider`, `MetadataStore`, `Renderer` |
| `errors.py` | 62 | Structured taxonomy: `ManifestError`, `SchemaError`, `RefError`, `OwnershipError`, `CollisionError`, `CapabilityError`, `DeleteUnsupportedError` (compat shim subclassing `CapabilityError`). Every error carries `reason` + `next_action` + optional `context`. | All error classes |
| `metadata.py` | 99 | Marker encode/decode; `MANAGER_NAME = "keeper-pam-declarative"`; field label `keeper_declarative_manager`. `utc_timestamp()` single source of truth. | `encode_marker`, `decode_marker`, `MARKER_FIELD_LABEL` |
| `normalize.py` | 305 | Manifest ↔ Commander `pam_import` JSON shape. `to_pam_import_json` / `from_pam_import_json`. Commander field-name leakage confined here. | `to_pam_import_json`, `from_pam_import_json` |
| `redact.py` | 133 | Redaction patterns (passwords, tokens, JWTs, KSM URLs, `keeper://` URLs added 2026-04-29, bearer); applied at renderer + error layers. | `redact` |
| `preview.py` | 129 | `DSK_PREVIEW=1` guard for unsupported schema surface (`rotation_settings`, `jit_settings`, `gateway.mode: create`, top-level `projects[]`). 14 cases in `tests/test_preview_gate.py`. | (preview helper APIs) |
| `rules.py` | 82 | Semantic validation beyond JSON schema: requires `pam_configuration_uid_ref` when configs exist; `pamRemoteBrowser` cannot carry `jit_settings`; `rotation` only on `pamMachine|pamDatabase|pamDirectory`. | (rule registry) |
| `schemas/pam-environment.v1.schema.json` | – | Packaged JSON schema (v1). | – |

## Where to land new work

| Change | File | Sibling to copy |
|---|---|---|
| New resource type (model + normalizer) | `models.py` + `normalize.py` | `PamRemoteBrowser` everywhere |
| New semantic rule | `rules.py` | existing `pamRemoteBrowser`-no-`jit_settings` rule |
| New ignored drift field | `diff.py::_DIFF_IGNORED_FIELDS` | `pam_configuration_uid_ref` entry |
| New error variant | `errors.py` | `CapabilityError` (carries `next_action`) |
| New preview-gated key | `preview.py` + `tests/test_preview_gate.py` | `rotation_settings` block |
| New marker payload field | `metadata.py` + DOR `METADATA_OWNERSHIP.md` first | `first_applied_at` field |

## Hard rules

- No imports from `keeper_sdk.providers.*` or `keeper_sdk.cli.*`.
- No subprocess, no `requests`, no Commander.
- Pydantic models: do not change `extra="allow"` policy.
- Marker constants (`MANAGER_NAME`, label) must match DOR `METADATA_OWNERSHIP.md` byte-for-byte.

## Reconciliation vs DOR

| DOR doc | Status | Evidence |
|---|---|---|
| `SCHEMA_CONTRACT.md` resource shapes | matched | `models.py`, `schemas/pam-environment.v1.schema.json` |
| `METADATA_OWNERSHIP.md` marker payload (`manifest`, `resource_type`, `parent_uid_ref`, `first_applied_at`, `last_applied_at`, `applied_by`) | matched | `metadata.py` (W1 reconciliation) |
| `DELIVERY_PLAN.md` exit codes | matched | `cli/main.py` + `errors.py`; documented in `docs/VALIDATION_STAGES.md` |
| Stage-5 `validate --online` bindings | matched | `interfaces.Provider.check_tenant_bindings()` + `tests/test_stage_5_bindings.py` |

## Known gaps (per `docs/SDK_DA_COMPLETION_PLAN.md`)

- Top-level `pamUser` standalone shape — schema/model open, planner unsupported (preview-gated → v1.1).
- Nested `pamUser.rotation_settings` — **UPSTREAM-GAP confirmed 2026-04-28 by live smoke**: offline diff fix PROVEN (`pam_settings.options` overlay + `managed` bool normalized in `diff.py`). Re-plan exit 2 after apply; Commander cannot write rotation `pam_settings`; no SDK code change until upstream Commander fix. Preview gates remain.
- RBI `pam_settings.options` — P3 RESOLVED (2026-04-28): `_enrich_pam_remote_browser_dag_options` in `providers/commander_cli.py` merges TunnelDAG `allowedSettings` → `pam_settings.options`; E2E smoke passed; P3.1 bucket table in `docs/COMMANDER.md`.
- `keeper-vault.v1` shared-folder rows — `VaultSharedFolder` / `diff_shared_folder` are modeled offline, and `SharingSharedFolder` is modeled in `keeper-vault-sharing.v1`; JSON schema acceptance and Commander write support for create/update/memberships/permissions remain preview-gated.
