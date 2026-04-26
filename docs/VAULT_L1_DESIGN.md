# Vault L1 — design (slice 1)

**Status:** `DRAFT` — technical body **complete** for implementation (PR-V1+).
Remove the `DRAFT` label and fill **§7** after integrator + reviewer sign-off.

**Links:** [ORCHESTRATION_PAM_PARITY.md](./ORCHESTRATION_PAM_PARITY.md) §3 PR train ·
[PAM_PARITY_PROGRAM.md](./PAM_PARITY_PROGRAM.md) ·
[CONVENTIONS.md](../keeper_sdk/core/schemas/CONVENTIONS.md) ·
[`keeper-vault.v1.schema.json`](../keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json)

---

## 1. Scope (slice 1)

### In scope (L1)

- **`records[]`** only for this slice: each record has `uid_ref`, `type`, `title`,
  optional `folder_ref`, optional `fields` / `custom` typed-field arrays, optional
  `keeper_uid` (discover binding), optional `notes`.
- **Record types:** start with **`login`** only (Commander `type` / template
  alignment to be verified against pinned Commander). Adding other built-in types
  is **L1.1** once `login` round-trips live.
- **Empty sibling blocks:** `record_types[]`, `attachments[]`, and `keeper_fill`
  may be **omitted or empty** in manifests; provider **must not** mutate them in
  L1.
- **Scale:** target first live proof with **≤ 5** declarative records in one
  shared folder; no batch migration story in L1.

### Out of scope until later slices

- **`record_types[]`** CRUD, **attachments** binary workflow, **keeper_fill**
  settings, rich payment/bank templates beyond what `login` needs.
- **Generic / file / other** record kinds not explicitly listed in “In scope”.
- **`keeper-vault-sharing.v1`** — see §5 (implemented **after** vault L1 is
  stable on `main`).
- Anything in [V2_DECISIONS.md](./V2_DECISIONS.md) **out-of-scope** list (MSP,
  `convert`, `verify_records`, …).

---

## 2. Folder & identity

### Folder scope

- Same as PAM today: **`KEEPER_DECLARATIVE_FOLDER`** (or CLI `--folder-uid`)
  identifies the shared folder where vault records are discovered and written.
- **Slice 1 does not** support multi-folder vault manifests; `folder_ref` may
  appear on records for **cross-family refs** per schema but L1 provider may
  **reject** non-local folder targets with a clear `CapabilityError` until a memo
  extends scope.

### Manifest name (`build_plan` / diffs)

- `keeper-vault.v1` JSON Schema currently has **no** top-level `name` key (unlike
  legacy PAM `version`+`name`).
- **Decision for L1:** use the **manifest file stem** as `manifest_name` when
  wiring `build_plan` / ownership marker `manifest` field, until a schema
  amendment adds optional `name:` (bundle that amendment with **V1** if product
  prefers explicit names in YAML).

### Ownership marker (parity with PAM)

- **Reuse** [`MARKER_FIELD_LABEL`](../keeper_sdk/core/metadata.py)
  (`keeper_declarative_manager`) and [`MANAGER_NAME`](../keeper_sdk/core/metadata.py)
  (`keeper-pam-declarative`) so `decode_marker` / adoption logic stay unified.
- **`resource_type` in marker JSON:** use the manifest record `type` string
  (e.g. `login`) so mixed PAM + vault folders remain distinguishable in discover.
- **`uid_ref`:** manifest `uid_ref` string (stable handle).
- **`manifest`:** manifest name from previous bullet (stem or future `name:`).
- **`parent_uid_ref`:** `null` for top-level vault records in L1 (nested vault
  not in slice 1).

Rationale: one field label and manager string across PAM + vault avoids a
second custom field and duplicate adoption rules.

---

## 3. Discover → `LiveRecord`

### Commander

- **List:** `keeper ls <FOLDER_UID> --format json` (same pattern as
  `CommanderCliProvider` PAM discover).
- **Detail:** `keeper get <RECORD_UID> --format json` per candidate UID from
  list (or batched if Commander supports — follow existing provider optimisations).
- **Marker:** read custom field **`keeper_declarative_manager`**; parse with
  `decode_marker`.

### Mapping

| Commander / JSON concept | `LiveRecord` field |
|--------------------------|-------------------|
| Record UID | `keeper_uid` |
| Title | `title` |
| Record type / template | `resource_type` (normalised string, e.g. `login`) |
| Folder UID if present | `folder_uid` |
| Full typed field bag (normalised keys) | `payload` |
| Parsed marker dict or `None` | `marker` |

**Normalisation:** provider owns translation from Commander `get` JSON to a
stable `payload` shape so `compute_diff` can compare against manifest-derived
expectations. Document the minimal key set for `login` in **V1** PR (code
comments + tests).

---

## 4. Plan / apply semantics

### Plan

- Reuse **`compute_diff`** / **`build_plan`** once manifests load into a typed
  vault model (or a family-dispatched loader) and `discover()` returns
  `LiveRecord` rows for vault records managed by this SDK.
- **Creates:** no `keeper_uid` on manifest record → create path.
- **Updates:** `keeper_uid` set and marker matches our manager + manifest name +
  `uid_ref` → update path; otherwise **CONFLICT** (same taxonomy as PAM).
- **Deletes:** only with **`--allow-delete`** and marker match; otherwise omit
  or CONFLICT.

### Apply

- **Create / update:** Commander APIs already used for PAM records where
  applicable (`record-add`, `record-update`, or in-process equivalents) — **V6**
  pins exact argv and JSON payloads against `.commander-pin`.
- **Delete:** `keeper rm <uid>` (or established provider path) with same gates
  as PAM.
- **Idempotency:** second `dsk apply` with unchanged manifest yields **clean
  plan** (0 creates/updates/deletes), same bar as PAM.

### `validate --online`

- **Slice 1:** extend `check_tenant_bindings` **or** a vault-specific hook only
  when manifest family is vault — e.g. folder reachable, record count sanity.
  Exact stage mapping documented in [VALIDATION_STAGES.md](./VALIDATION_STAGES.md)
  when implemented (likely stage 5 parity).

### Semantic `login` diff (L1 limits)

`compute_vault_diff` compares manifest ``login`` ``fields[]`` to Commander-shaped
live payloads by flattening **scalar** typed entries to a ``label → value`` map
(labels matched case-insensitively when live data uses top-level keys). Operators
should assume:

- **Duplicate field labels** in ``fields[]`` collapse in the flatten map — drift
  can be hidden or attributed to the wrong slot until apply semantics are tightened.
- **Non-scalar / structured** typed values (nested dicts, multi-value shapes the
  flattener skips) are **out of scope for L1** equality — false “clean” diffs are
  possible until **L1.1** extends the rules.
- **Commander pin / tenant policy skew** — unit tests encode expectations for the
  pinned Commander JSON shape; other versions or enterprise flags may differ.

A **clean** `plan` / `diff` / `validate --online` is **evidence**, not a formal
correctness proof, until **G6** live transcripts and matrix rows cover the slice.

### Concurrent edits vs `validate --online`

Stages 4–5 (and offline **plan** / **diff**) observe tenant state **only at call
time**. Mobile clients, admins, or a second automation can change records **after**
`validate --online` and **before** `apply`. The SDK does **not** lock records —
rerun **plan** / **diff** or `validate --online` immediately before **apply** when
races matter.

### Commander `login` UPDATE (v3 JSON)

**UPDATE** uses in-process ``RecordEditCommand`` with full v3 ``data`` JSON; the
provider only proceeds when the cached record is **version 3**. If Commander logs
an error and returns without calling ``api.update_record_v3``, the provider raises
``CapabilityError`` (stderr tail in the reason) instead of silently succeeding.

---

## 5. `keeper-vault-sharing.v1` relationship

- **Order:** implement **after** `keeper-vault.v1` L1 is merged and live-proofed
  (ORCHESTRATION **V7**), unless a separate product memo explicitly allows
  parallel work with **disjoint** provider files and **two** integrators.
- Sharing introduces **ACL / folder grant** semantics; do not block vault L1 on
  sharing design.

---

## 6. CLI / loader dispatch (decision placeholder)

Pick **one** in **V4** (do not ship both) — **Option A** is implemented for
``keeper-vault.v1`` + ``pam-environment.v1`` via :func:`load_declarative_manifest`
and CLI dispatch; other families remain schema-only at the CLI until typed slices
land:

- **Option A — Dispatch inside `load_manifest`:** resolve family; if vault,
  return a new typed `VaultManifest` (or union) from the same entrypoint; graph
  / plan code branches on type.
- **Option B — Explicit subcommand or flag:** e.g. `dsk plan-vault` / `--family
  keeper-vault.v1` while `load_manifest` stays PAM-only for a transition window.

This design **recommends Option A** long-term; Option B is acceptable only as a
**temporary** shim if graph/planner refactors are too large for one PR.

---

## 7. Sign-off

| Role | Name | Date |
|------|------|------|
| Integrator | | |
| Reviewer | | |

---

## 8. Implementation pointer (PR-V1)

- **Typed models + loader:** `keeper_sdk/core/vault_models.py` — `VaultManifestV1`,
  `VaultRecord`, `load_vault_manifest()` (JSON Schema via `validate_manifest` then
  Pydantic + L1 `login`-only rule). Public re-exports: `keeper_sdk.core`.
- **Tests:** `tests/test_vault_models.py`.
- **Graph (PR-V2):** `keeper_sdk/core/vault_graph.py` — `build_vault_graph`,
  `vault_record_apply_order`; tests `tests/test_vault_graph.py`.
- **Diff + mock plan (PR-V3):** `keeper_sdk/core/vault_diff.py` —
  `compute_vault_diff`; :class:`~keeper_sdk.providers.mock.MockProvider` for
  apply; tests `tests/test_vault_mock_provider.py`.
- **Loader + CLI (PR-V4):** :func:`keeper_sdk.core.manifest.load_declarative_manifest`;
  ``dsk plan`` / ``diff`` / ``apply``; ``dsk validate --json`` modes
  ``vault_offline`` / ``vault_online`` (``--online`` requires Commander + folder
  scope; discover + diff smoke — see ``docs/VALIDATION_STAGES.md``).
- **Commander (PR-V5/V6):** :class:`~keeper_sdk.providers.commander_cli.CommanderCliProvider`
  — vault ``discover()`` keeps ``login`` rows; ``apply_plan()`` record-add, **UPDATE**
  merges planner field drift (Commander ``RecordEditCommand`` JSON path — **record
  version 3** in cache only) then marker refresh, ``rm`` for deletes.

## 9. Revision history

| Date | Change |
|------|--------|
| 2026-04-26 | Initial slice-1 technical body for PR-V0 / Phase A. |
| 2026-04-26 | PR-V1: `vault_models.py` + tests (sign-off still pending on §7). |
| 2026-04-27 | §8: `validate --online` / `vault_online` JSON mode (PR-V4+); no §7 sign-off. |
| 2026-04-27 | §4: semantic `login` diff limits, concurrent-edit caveat, Commander UPDATE / `CapabilityError` guard (no §7 sign-off). |
