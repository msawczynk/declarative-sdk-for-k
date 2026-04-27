# PAM parity program — when a family is “ready”, not scaffolded

PAM parity acceptance criteria are tracked alongside this document;
operator-side delivery cadence is not part of the public SDK.

This document defines what **“supported like PAM”** means in *this* repo, why the
README must **not** claim universal GA until those gates pass, and the phased
work to lift each manifest family from **schema-only** to **production**.

## The PAM bar (Definition of Done)

Treat `pam-environment.v1` + `CommanderCliProvider` + `MockProvider` as the
reference. A manifest family **F** clears the PAM bar only when **all** of the
following are true:

1. **Schema** — Packaged JSON Schema under `keeper_sdk/core/schemas/` with
   `x-keeper-live-proof.status: supported` (or `preview-gated` with explicit
   scope in `CHANGELOG.md`), not `scaffold-only` / `upstream-gap` / `dropped-design`.
2. **Validation** — `dsk validate` loads **F**’s schema by manifest `schema:` key
   (✅ **Phase 0 landed:** `keeper_sdk/core/schema.py` registry +
   `resolve_manifest_family`; legacy PAM uses `version`+`name` without `schema`.)
3. **Typed core** — Pydantic (or equivalent) models round-trip the manifest and
   are used in plan/diff, not “dict-only” passthrough for **F**.
4. **Discover** — Commander-backed discovery returns `LiveRecord` shapes that
   `compute_diff` understands for **F** (folder scope, ownership markers or
   agreed substitute).
5. **Plan / apply** — `dsk plan` / `dsk apply` invoke the correct Commander
   surfaces for **F** with the same exit-code contract as PAM; deletes remain
   gated and marker-aware where applicable.
6. **Tests** — Offline tests cover validate → plan → apply (mock) and
   contract tests for Commander payloads; no family ships on schema CI alone.
7. **Live proof** — Sanitized transcript under `docs/live-proof/` referenced
   from the schema’s `x-keeper-live-proof.evidence`, with live smoke on a
   lab tenant (per `docs/V2_DECISIONS.md` Q4).
8. **Matrix** — `docs/CAPABILITY_MATRIX.md` / snapshot row shows **F** as
   supported, not “scaffold-only”.

Until **all eight** hold, the family is **not** “GA like PAM” regardless of how
complete the JSON file looks.

## Current inventory (honest snapshot)

| Family | Packaged schema | Wired into `dsk` core + Commander provider | Typical `x-keeper-live-proof` |
|--------|-----------------|------------------------------------------|--------------------------------|
| `pam-environment.v1` | yes (`pam-environment.v1.schema.json`) | **yes** | `supported` on proven paths |
| `keeper-vault.v1` | yes | **partial** — `dsk validate` (offline + `--online` Commander + folder), `plan` / `diff` / `apply` on mock + Commander L1 **`login`** (create + **v3 JSON UPDATE** via `RecordEditCommand` + `return_result` guard, marker refresh, `rm`); `compute_vault_diff` semantic scalar **login** compare (manifest `fields[]` vs flattened live — see [`VAULT_L1_DESIGN.md`](./VAULT_L1_DESIGN.md) §4); matrix + `supported` live proof still **G6 / V8** | `scaffold-only` |
| `keeper-vault-sharing.v1` | yes | **no** | `scaffold-only` |
| `keeper-enterprise.v1` | yes | **no** | scaffold / partial slices in design memos only |
| `keeper-integrations-identity.v1` | yes | **no** | scaffold-only |
| `keeper-integrations-events.v1` | yes | **no** | scaffold-only |
| `keeper-ksm.v1` | yes | **no** (KSM bootstrap + helpers are separate CLI/SDK paths) | scaffold / partial |
| `keeper-pam-extended.v1` | yes | **no** | scaffold-only / stubs |
| `keeper-epm.v1` | yes | **no** | watchlist (V2 Q5) |
| `keeper-security-posture.v1` | yes (intentional trap) | **no** — use `dsk report` verbs | `dropped-design` |

Runtime verbs (`dsk report`, future `dsk run`) are **not** manifest families; they
have their own redaction + argv bars (`docs/V2_DECISIONS.md` Q3).

## Phased plan to earn a “everything GA” README

Workstreams are ordered so each unlocks honest README tightening without lying
about Commander coverage.

### Phase 0 — Registry and honesty (foundation)

**Shipped (2026-04-26):**

- `keeper_sdk/core/schema.py`: `SCHEMA_RESOURCE_BY_FAMILY`, `resolve_manifest_family`,
  `load_schema_for_family`, `packaged_schema_families`; `validate_manifest` resolves
  family + rejects `dropped-design` families before instance validation.
- Optional `schema: pam-environment.v1` on PAM manifests (JSON Schema + canonicalise).
- `keeper_sdk/core/manifest.py`: `read_manifest_document`; `load_manifest` refuses
  non-PAM typed loads with a clear `ManifestError`.
- `dsk validate`: JSON Schema for any packaged family. **`pam-environment.v1`**
  runs uid_ref graph offline and full stages 4–5 with `--online`. **`keeper-vault.v1`**
  runs `build_vault_graph` offline (stages 1–3 analogue) and stages 4–5 with
  `--online` + Commander + folder scope (no PAM gateway probe).

**Still open in later phases:**

- Typed models + Commander/provider slices for non-PAM families that are still
  **no** or **scaffold-only** in the [inventory table](#current-inventory-honest-snapshot)
  below (excluding the **`keeper-vault.v1` L1 partial** row, which already has models + graph + mock + Commander slice — **G6/V8** + §7 remain).
- README hero stays PAM-first until those land.

### Phase 1 — Vault + sharing (highest agent value)

**1a (shipped incrementally):** `examples/scaffold_only/*.yaml` samples; CI
validates them; `dsk validate --json` exposes `schema_only`, `pam_full`,
`vault_offline`, and `vault_online` (latter requires Commander + folder) for
agents.

- **`keeper-vault.v1` L1 (on `main`):** typed models (`vault_models.py`), graph
  (`vault_graph.py`), `compute_vault_diff` + mock round-trip, Commander discover
  (`login` filter) + apply (create, **v3** `RecordEditCommand` UPDATE + `return_result`
  guard, marker, `rm`), `dsk validate --online`, semantic scalar `login` diff — see
  [`VAULT_L1_DESIGN.md`](./VAULT_L1_DESIGN.md) §4. **PAM-bar closure** still needs
  live proof + matrix + `VAULT_L1_DESIGN` §7 and
  [`docs/live-proof/README.md`](./live-proof/README.md).
- **`keeper-vault-sharing.v1`:** typed models + graph + mock + Commander + live
  proof (reuse vault patterns).

### Phase 2 — Enterprise + integrations

- Enterprise nodes/users/roles/teams: align payloads to pinned Commander;
  graduate matrix rows from “scaffold-only” only after live proof slices.
- Split integrations families: identity vs events; respect `uid_ref` grammar
  from `keeper_sdk/core/schemas/CONVENTIONS.md`.

### Phase 3 — KSM + pam-extended

- `keeper-ksm.v1`: connect schema to existing bootstrap / share flows where
  declarative; avoid duplicating `dsk bootstrap-ksm` semantics in two ways.
- `keeper-pam-extended.v1`: lift `maxItems: 0` stubs when Commander paths exist;
  mark `upstream-gap` until Commander exposes stable idempotent writers.

### Phase 4 — EPM and posture

- **EPM**: only after V2 Q5 triggers (audit + customer + licensed smoke).
- **Posture**: no manifest family; expand `dsk report` with memos per P17 bar.
  README “all GA” explicitly **excludes** dropped-design posture-as-manifest.

### Phase 5 — README top-level GA refresh

When **every non-dropped family** that remains in product scope hits the PAM bar,
update the `README.md` hero paragraph to state **multi-family GA** and link this
file as retired / archived. Until then, the README stays **PAM-first** with a
clear per-family table.

## Devil’s-advocate guardrails

- **No README marketing ahead of Phase 0–1** — scaffold JSON is not “shipped”
  capability; it is design and CI surface only.
- **Spikes do not clear the bar** — a demo script does not replace live proof +
  matrix + tests.
- **V2 boundaries stay explicit** — MSP, `convert`, `pam_debug`, etc. remain out
  of declarative scope until product re-opens them; the README can still say
  “platform GA for DSK” while listing those as Commander-direct by design.

## Owners

- **Product** — live tenant, pin bumps, customer priority, which family
  is next after vault L1.
- **Implementers** — registry + per-family provider slices + tests + proof
  transcripts.
- **Docs** — README readiness table + `CAPABILITY_MATRIX.md` stay mechanically
  aligned with `x-keeper-live-proof` and this program.
