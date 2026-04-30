# `keeper_sdk/` — package scaffold

Stable 1.x import path. Public surface is `keeper_sdk.core` + `keeper_sdk.providers`.
Pure-Python; no top-level I/O.

## Sub-packages

| Path | Role | Land new work? | Local SCAFFOLD |
|---|---|---|---|
| `core/` | Pure manifest/schema/graph/diff/planner/redact/preview. Zero subprocess. | YES for any pure logic | [`core/SCAFFOLD.md`](./core/SCAFFOLD.md) |
| `cli/` | `dsk` Click entrypoint + Rich renderer; orchestrates exit codes. | YES for new CLI verbs/flags | [`cli/SCAFFOLD.md`](./cli/SCAFFOLD.md) |
| `providers/` | `MockProvider` (offline) + `CommanderCliProvider` (live). Implement `core.interfaces.Provider`. | YES for new backends | [`providers/SCAFFOLD.md`](./providers/SCAFFOLD.md) |
| `auth/` | `EnvLoginHelper` + `KsmLoginHelper` + helper-protocol contract. | YES for new login backends | [`auth/SCAFFOLD.md`](./auth/SCAFFOLD.md) |
| `secrets/` | KSM app bootstrap (`bootstrap.py`), KSM config reader (`ksm.py`), inter-agent bus (`bus.py` — preview/sealed). | YES for KSM / bootstrap; bus remains skeleton until wire-format gate | [`secrets/SCAFFOLD.md`](./secrets/SCAFFOLD.md) |

## Top-level files

| File | Purpose |
|---|---|
| `__init__.py` | Re-exports stable surface (`Manifest`, `Plan`, `build_graph`, `compute_diff`, …); pins package `__version__`. |

## Hard rules

- `core/` MUST NOT import from `providers/` or `cli/` or `auth/`. One-way deps only.
- `providers/` MUST NOT touch `keeper_dag.*` directly — Commander surfaces only (subprocess `keeper` CLI or in-process `keepercommander.*`).
- Public surface frozen for v1.x. Breaking renames (`keeper_sdk` → `declarative_sdk_k`) deferred to v2.0 (V1_GA_CHECKLIST hardening row).

## Design contract

- Manifest = source of truth. `plan` = delta. `apply` = execute + write ownership marker (`MANAGER_NAME = "keeper-pam-declarative"`).
- SDK never touches records without its marker. `compute_diff(adopt=False)` default emits CONFLICT for unmanaged title-matches.
- Exit-code contract enforced in `cli/main.py`; see `docs/VALIDATION_STAGES.md`.

## Reconciliation note

Matches DOR (`keeper-pam-declarative/SCHEMA_CONTRACT.md` + `METADATA_OWNERSHIP.md`)
as of last AUDIT.md pass. Drift policy: capability mirror in `docs/CAPABILITY_MATRIX.md`
+ `scripts/sync_upstream.py` (CI `drift-check`).
