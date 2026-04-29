# MSP family — design memo (`msp-environment.v1`, slice 1)

**Status:** `DRAFT` — design-only; no packaged schema, models, or provider code
until a follow-on implementation sprint lands.

**Links:** [V2_DECISIONS.md — Q5](./V2_DECISIONS.md#q5--msp-and-epm-in-product-scope) ·
[Vault L1 design (memo shape reference)](./VAULT_L1_DESIGN.md) ·
[PAM parity program (family bar + phased roadmap)](./PAM_PARITY_PROGRAM.md) ·
[VALIDATION_STAGES.md](./VALIDATION_STAGES.md) (exit codes / stages when this family
wires into `dsk validate`) ·
[CONVENTIONS.md](../keeper_sdk/core/schemas/CONVENTIONS.md)

**Upstream Commander surface (studied):** `keepercommander.commands.msp` in a local
`Commander` checkout; SDK dependency pin: `keepercommander>=17.2.16,<18` (developer
`pip show` in this repo: **17.2.15** at time of writing). Class and argv details
in §6.

---

## 1. Scope

### Un-drop evidence

Per [V2_DECISIONS.md Q5](./V2_DECISIONS.md#q5--msp-and-epm-in-product-scope), the
**MSP “dropped-design” status was rescinded** on **2026-04-27 (Sprint 7h-56)** when:

- An MSP **parent tenant** for lab work existed (master admin identity and KSM
  pointer under workspace **“MSP tenant identity reference (canonical)”** — see
  §7 and the workspace journal; this memo does not repeat secret material).
- **Maintainer** confirmed product interest in **declarative** MSP.
- A hardened **read-only** smoke path (`keeper-vault-rbi-pam-testenv` —
  `scripts/msp_smoke.py`) was available to capture **sanitized** `msp-info` /
  license-snapshot **envelopes** for design and future contract tests.

This memo is the **Sprint 7h-56** deliverable named in Q5: it specifies the first
`msp-environment.v1` slice so implementation can start without re-deriving
upstream Commander behavior from chat.

### In scope (slice 1)

- New schema family key **`msp-environment.v1`** with a minimal **typed**
  manifest: MSP parent metadata + **`managed_companies[]`**.
- **End-to-end lifecycle** for **one** canonical write path matching Q5: **add
  managed company** (CLI verb **`msp-add`**, Commander **`MSPAddCommand`**) —
  expressed in the plan as a **`create_mc`** (or equivalent) op together with
  **validate / plan / diff / apply** (same exit-code contract as
  `pam-environment.v1` per [PAM_PARITY_PROGRAM.md](./PAM_PARITY_PROGRAM.md)).
- **Read path** for diff input aligned with the **smoke harness** probe
  `probes[name=msp-info].rows` (see §3 and §5) — that is, the **same JSON row keys**
  the harness emits after **fingerprinting** sensitive identifiers.
- **Update** and **remove** managed companies **in the same design**: provider
  hooks are **`msp-update` / `MSPUpdateCommand`** and **`msp-remove` /
  `MSPRemoveCommand`**; slice 1 may **ship** only `create` first, but the memo
  defines **`update_mc` / `delete_mc`** ops so a second sprint does not redesign
  the tree.

### Explicit out of scope (this slice’s implementation tranche)

The following are **deferred** so that slice 1 stays one Commander write family
on par with the first `pam-environment.v1` tranche (single verb proven live,
then expand):

- **License pool manipulation** beyond what **create/update MC** already implies
  (`msp-update` is the Commander surface for **per-MC** license changes; the SDK
  does not model `msp pool …` in slice 1 — see open questions).
- **`msp-permits`** and MSP restriction **editing** (read may appear in
  `params.enterprise` for validation messages only).
- **`msp-convert-node`**, **`msp-copy-role`**, **distributor** flows.
- **EPM / PEDM** — [V2 Q5](./V2_DECISIONS.md#q5--msp-and-epm-in-product-scope) keeps
  EPM as a **separate** trigger; do not conflate with MSP slice 1.

### Infrastructure note (non-binding)

Workspace journal records **infrastructure reuse** (e.g. **Rocky** lab host and
**VPS** used for other Acme-lab work) for **operator** convenience. The SDK
**does not** require those hosts for `msp-add`; they matter for **org-specific**
harnesses and **live-proof** execution context, not for schema keys.

---

## 2. Schema family `msp-environment.v1`

### Top-level shape (normative for implementation)

| Key | Required | Description |
|-----|----------|-------------|
| `schema` | **yes** | Must be the literal `msp-environment.v1` (parallels `pam-environment.v1`’s explicit family pin; see [pam-environment.v1 schema](../keeper_sdk/core/schemas/pam-environment.v1.schema.json) `schema` const pattern). |
| `name` | **yes** | Human manifest name (used in plan summaries, ownership / audit text). |
| `manager` | optional | Declarative **manager** string; **TBD** whether MSP reuses the same `keeper_declarative_manager` marker family as PAM/vault or uses enterprise-only metadata — see §10. |
| `managed_companies` | **yes** (array, may be empty) | The desired state of child **Managed Company** (MC) rows under the MSP parent. |
| `policies` | optional | **Reserved** bucket for future MSP-level defaults (e.g. echoing **msp permits** allow-lists in manifest form). **Not** in slice 1. |

`x-keeper-live-proof` on the **future** `msp-environment.v1.schema.json` should
follow the pattern in
[`keeper-vault.v1.schema.json`](../keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json)
and [pam-environment.v1](../keeper_sdk/core/schemas/pam-environment.v1.schema.json):
`status`, `evidence` path to a **sanitized** transcript, `since_pin` / Commander
commit pin as appropriate, and a short `notes` field. Until live proof exists,
`preview-gated` or `scaffold-only` is honest per
[PAM_PARITY_PROGRAM.md](./PAM_PARITY_PROGRAM.md).

### YAML stub (illustrative — not a shipped schema)

```yaml
# Illustrative only — no JSON Schema file is part of this memo.
schema: msp-environment.v1
name: acme-msp-lab
manager: keeper-msp-declarative   # TBD: marker parity vs PAM
managed_companies:
  - name: "Acme Widgets MC"
    plan: business
    seats: 10
    file_plan: null
    addons: []                    # TBD: list of addon spec objects or strings
# policies: {}                    # reserved
```

---

## 3. Managed company entity

### 3.1 `msp-info` (Commander) — table columns and enterprise JSON

`MSPInfoCommand` in `keepercommander/commands/msp.py` prints managed companies
from `params.enterprise['managed_companies']`. The **default** (non-verbose) row
**header** is:

`company_id`, `company_name`, `node`, `plan`, `storage`, `addons`, `allocated`, `active`

With **verbose** mode, `node_name` is inserted after `node` in the header; **plan**
in the data row is the **raw** `product_id` string in verbose mode, whereas in
**non-verbose** mode the **plan** cell is the **display** name from
`constants.MSP_PLANS` when mapping succeeds.

| Column / key | Source field on MC dict | Semantics / notes |
|----------------|-------------------------|-------------------|
| `company_id` | `mc_enterprise_id` | Integer **Managed Company** enterprise id. |
| `company_name` | `mc_enterprise_name` | Case-sensitive for display; Commander matching for CLI is case-insensitive on **name** string. |
| `node` / `node` path | `msp_node_id` via `get_node_path` | Hierarchical path string; verbose adds parallel **`node_name`**. |
| `plan` | `product_id` | **Non-verbose:** mapped to plan **code / display** via `MSP_PLANS`. **Verbose:** **unmapped** `product_id` string remains in the `plan` column (implementation detail: **diff** should normalise to one representation — open question). |
| `storage` | `file_plan_type` | Mapped through `MSP_FILE_PLANS` to a **display** name for the file plan. |
| `addons` | `add_ons` | **Non-verbose:** **count of addon names** (integer), **not** a structured list. **Verbose:** per-addon list of **strings** (addon name, or `name:seats` when seats apply). |
| `allocated` | `number_of_seats` | **Seat cap**; `2147483647` (or large sentinel) displayed as **-1** in Commander output. |
| `active` | `number_of_users` | **Current active users** — **read-only** for provisioning; not settable via `msp-add`. |

**Drift warning — `addons`:** the **read** table’s `addons` column is **not**
stable between non-verbose (integer **count**) and verbose (list of **strings**).
The **smoke harness** always uses **verbose** JSON (see below), so the **SDK
diff** should treat the harness row shape as canonical for **envelope**-based
tests.

### 3.2 Smoke harness `msp-info` row shape (sanitized envelope)

`keeper-vault-rbi-pam-testenv/scripts/msp_smoke.py` ** `_probe_msp_info`** calls
`MSPInfoCommand().execute(params, verbose=True, format="json")` and rewrites each
row to a **fingerprinted** form:

- `company_id` — **fingerprinted** (treat as opaque in public artifacts).
- `company_name` — **fingerprinted** (stable within a run for equality tests only
  if the harness also fingerprints names; operators should use **manifest name**
  for identity in §5).
- `node_id` — fingerprinted from the **node** column of the report row (path
  string in Commander output, hashed as `node` type).
- `node_name` — fingerprinted.
- `plan`, `storage` — **passed through** from Commander JSON.
- `addons` — list (default `[]`); in verbose **msp-info** this is a **list of
  string tokens** (not the non-verbose integer count).
- `allocated` — **integer** seat allocation (reuses label **allocated** for the
  Commander column **“allocated”** in the table, which is **licence count** from
  `number_of_seats` per Commander).
- `active` — **integer** (active user count).

This row shape is the **contract** for “**envelope** diff” in CI and in **public**
transcripts. The **in-process** provider will use **unredacted** `query_enterprise`
data for stable **`mc_enterprise_id`** and **exact** strings.

### 3.3 `msp-add` / `MSPAddCommand` (write)

Registered as **`commands['msp-add']`**. The **argparse** surface:

| Argument | Option | Type | Semantics |
|----------|--------|------|------------|
| (positional) | `name` | str | **Managed company name** (required for CLI; passed as `name` in `execute` kwargs). |
| `--node` | `node` | str | Optional **node name or id**; if omitted, Commander picks a **default root** node (if none, command errors). |
| `-s` / `--seats` | `seats` | int | **Maximum licences**; **-1** means unlimited (internally may map to a large int). Omitted / non-int is treated as **0** in the API request. |
| `-p` / `--plan` | `plan` | choice | **Required in CLI** — must be a valid `MSP_PLANS` **string** (second element of each tuple in Commander). **Note:** the Python `execute` also applies **permit** fallbacks and defaults when re-used programmatically. |
| `-f` / `--file-plan` | `file_plan` | str | **File storage** plan name (one of the string choices from `MSP_FILE_PLANS` rows, matched case-insensitively in code). |
| `-a` / `--addon` | `addon` | repeatable | Each value is `ADDON` or `ADDON:SEATS` for seat-bearing addons. |

**Internal API** (for integrators): `command` = `enterprise_registration_by_msp`
with `node_id`, `product_id`, `seats`, `enterprise_name`, `encrypted_tree_key`, …,
optional `file_plan_type` and `add_ons` list. **No Python code** in this repo yet;
listed here so **schema field names** align with what **Commander** already sends.

### 3.4 `msp-update` / `MSPUpdateCommand` (write) — for parity with plan ops

Kwargs of interest: **`mc`** (target MC **name or id**), optional **`node`**,
**`name`** (rename), **`plan`**, **`seats`**, **`file_plan`**, repeat **`--add-addon`**
/ **`--remove-addon`**. The implementation performs a **read/modify/write** on
`enterprise_update_by_msp` with a merged addon map (with **RBI / Connection
Manager** coupling rules in Commander). Slice 1 may **not** call update from
`apply` until a follow-on, but the **field list** is required for the **§4**
examples and the **op** list in §5.

### 3.5 `msp-remove` / `MSPRemoveCommand` (write)

Kwargs: **`mc`** (name or id), **`force`** to skip the interactive **y/n**
prompt. The SDK’s non-interactive **apply** will require either **`--force`**
semantics in the Commander integration layer or a **separate** provider API that
skips the prompt; **TBD** (open question).

### 3.6 Read vs write — field presence matrix

| Concern | `msp-info` (verbose / harness) | `MSPAddCommand` | `MSPUpdateCommand` / `msp-remove` |
|---------|-------------------------------|-----------------|-------------------------------------|
| MC **identity** (integer id) | `company_id` (fp in envelope) | Output only (`enterprise_id` in result) | **Keyed** by `mc` |
| **Name** | `company_name` | **positional** `name` | `-n` / `name` to rename; **mc** to select |
| **Plan** | `plan` (see normalisation caveat) | **required** `-p` / `plan` | `-p` / `plan` |
| **Seats (cap)** | `allocated` | `-s` / `seats` | `-s` / `seats` |
| **File plan** | `storage` | `-f` / `file_plan` | `-f` / `file_plan` |
| **Addons** | `addons` (list of strings) | `-a` / `addon` (repeat) | add/remove **delta** list |
| **Active users** | `active` | **not settable** | not used |
| **Node** | in path / `node_id` + `node_name` | `--node` | `--node` |

**One-line drift summary:** The **read** path exposes **`active` users** and
**ambiguous `plan` display** (verbose vs non-verbose); the **add** path never sets
`active` and **requires** a **plan** on the wire for new MCs. **Addon** shapes
differ: **harness** = list of strings, **add** = repeatable CLI tokens,
**update** = add/remove with merge semantics.

---

## 4. Manifest examples

### 4.1 Minimal — one MC, default plan intent

```yaml
schema: msp-environment.v1
name: msp-baseline
managed_companies:
  - name: "Contoso East"
    plan: business
    seats: 5
```

### 4.2 With addons (declare desired addon mix)

Per **Q6 TENTATIVE** (§10): addons are **structured** `{name, seats}` only.
The bare-string shorthand `connection_manager:5` originally drafted here was
**rejected** by the P0 JSON Schema and is corrected below (Sprint 7h-58 P1
worker finding):

```yaml
schema: msp-environment.v1
name: msp-with-addons
managed_companies:
  - name: "Fabrikam Managed"
    plan: enterprise
    seats: 25
    file_plan: enterprise  # TBD: must match Commander file-plan string table
    addons:
      - name: connection_manager
        seats: 5
      - name: remote_browser_isolation
        seats: 5
```

(**RBI+CM** ordering rules exist in Commander and must be preserved on
`apply` — the structured shape lets the diff layer reason about per-addon
seat counts without re-parsing colon-separated strings.)

### 4.3 Custom seat allocation (and `node` deferred)

The original draft used `seats: -1` and a top-level `node:` key on each MC.
Both were **invalid** against the P0 schema (seats minimum is 0;
`additionalProperties: false` on `managed_company` rejects unknown keys
including `node`). Sprint 7h-58 P1 worker finding — corrected:

```yaml
schema: msp-environment.v1
name: msp-large
managed_companies:
  - name: "Adatum Corp"
    plan: business
    seats: 0   # 0 = "claim no seats yet"; "unlimited" encoding deferred — see open Q
    file_plan: null
    addons: []
```

Open follow-ups (deferred to a future memo update, not blocking P0–P1):

- **Unlimited-seats encoding:** Commander accepts large-int or pool-cap;
  manifest encoding TBD. For now schema requires `seats >= 0`.
- **Node placement:** `node` (path or numeric id) is a Commander param on
  `MSPAddCommand` (see §6) but not yet a schema field. Add as optional
  `node:` (string) on `managed_company` in a P1.5 schema bump if
  multi-node MSP placement is required for slice 1; otherwise defer to
  P2/P3 once graph/diff lands.

---

## 5. Diff semantics

### 5.1 Input (live / harness)

- **Primary:** `probes` entry **`name: msp-info`**, field **`rows`**: array of
  objects with keys as in the smoke **safe_rows** (§3.2). UIDs and names in a
  **public** transcript are **fingerprinted**; **do not** use `company_id` as a
  stable public identifier.
- **Optional overlay:** the **in-process** Commander provider uses
  `query_enterprise` **unredacted** `managed_companies` so **`mc_enterprise_id`**
  is available for idempotent **update** and **delete** and for avoiding duplicate
  creates by name.

### 5.2 Desired state (manifest)

The typed manifest’s **`managed_companies[]`** after **normalisation** to a
**ManagedCompanyKey** (see below).

### 5.3 Identity key

- **Primary key for declarative diff:** **managed company `name` string**
  (case-folding **TBD** — Commander `get_mc_by_name_or_id` uses **case-insensitive
  name** match for string inputs; implementation should match that).
- **Internal stable id** after first create: **`mc_enterprise_id`**, available in
  live `params.enterprise` but **not** required in the manifest for slice 1
  (optional `keeper_id` or similar field may be **added in a later memo** to
  support renames and imports).

### 5.4 Fingerprint vs real id

| Context | `company_id` / MC id | `company_name` |
|---------|----------------------|----------------|
| **Public envelope** / CI | **fingerprinted** (opaque, comparable only within the same run’s convention) | **fingerprinted** in harness; **do not** diff manifest name to envelope `company_name` without a **private** pre-normalisation step |
| **Provider** (Commander) | **Real** integer `mc_enterprise_id` | **Real** string `mc_enterprise_name` |
| **Manifest** | Omitted in slice 1 (optional in future) | **Authoritative desired name** for **create**; match key for **update** |

**Rule:** The **dsk** diff for **public** tests compares **normalised** rows after
**either** the provider supplies a private mapping table (name → last-known id) or
tests run **unfingerprinted** in a private harness — **TBD** by implementation.

### 5.5 Output ops (plan)

**Ordered** list of abstract ops (map 1:1 to provider/Commander in §6):

1. **`create_mc`** — manifest has **name** not present in live set (by key).
2. **`update_mc`** — same key, drift in `plan` / `seats` / `file_plan` / `addons` /
   `node` (whatever subset slice implements).
3. **`delete_mc`** — live row exists, **name** (or id) not in desired set — only
  with `--allow-delete` and **explicit** product rules (PAM bar: no silent
  deletes; align with [PAM_PARITY_PROGRAM.md](./PAM_PARITY_PROGRAM.md)).

`noop` / **conflict** rows follow the same taxonomy as PAM and vault: **unmanaged
MCs** (not in manifest) are **out of band**; only manifest-declared or
marker-owned rows are fair game — **marker strategy for MC** is a §10 item.

### 5.6 Normalisation (guidance for implementers)

- **Seats:** map `-1` and **large sentinels** to a **canonical** int for diff.
- **Addons:** **sort** and **split** `name:seats` for comparison; see Commander’s
  verbose ordering for `msp-info`.
- **Plan:** **normalise** to Commander **`MSP_PLANS` string** (second tuple
  element) for equality.

---

## 6. Provider hooks (Commander)

**Import path:** `keepercommander.commands.msp` (Commander source tree; package
`keepercommander` in site-packages after install).

| Verb | Class | `register_commands` key | When to use |
|------|--------|------------------------|------------|
| `msp-add` | **`MSPAddCommand`** | `'msp-add'` | **`create_mc`** — after validation of permits / duplicate name |
| `msp-update` | **`MSPUpdateCommand`** | `'msp-update'` | **`update_mc`** |
| `msp-remove` | **`MSPRemoveCommand`** | `'msp-remove'` | **`delete_mc`** (subject to gating) |

**Note:** The upstream code **does not** define `MSPAddManagedCompanyCommand` — the
add verb is implemented as **`MSPAddCommand`**. Downstream design docs and issue
text may still say `msp-add-mc`; map that phrase to **`msp-add`**.

**Parameters (execute kwargs — mirror argparse):**

- **`MSPAddCommand`:** `name`, `plan` (required on CLI; programmatic defaults
  exist in `execute`), `node`, `seats`, `file_plan`, `addon` (list when repeated
  on parser — confirm integration bridge passes **list of strings** as expected).
- **`MSPUpdateCommand`:** `mc` **required**; `node`, `name`, `plan`, `seats`,
  `file_plan`, `add_addon` (list), `remove_addon` (list).
- **`MSPRemoveCommand`:** `mc` **required**; `force` (bool) to skip confirmation.

`MSPInfoCommand` is used for **discover** / **diff** input (`msp-info`), not for
**apply**.

Non-goals in slice 1: **`GetMSPDataCommand` (`msp-down`)** as a separate sync
step unless `query_enterprise` is insufficient in practice (open question).

**Pinned version:** this memo was written against the Commander module layout in
`keepercommander` **17.2.15** (installed) within the project’s
**`>=17.2.16,<18`** range. Re-verify signatures before merge if the pin drifts.

---

## 7. Live-proof plan

### 7.1 Lab references (non-secret)

- **KSM record UID (credentials pointer):** `gu9SvWBHRlPsmRhtjvRX9A` (see
  workspace JOURNAL — **“MSP tenant identity reference (canonical)”**; do not
  commit secrets; UID is a pointer, not a password).
- **Master admin (identity only):** `msawczyn+msplab@acme-demo.com` — an **MSP
  parent** dev tenant, distinct from the general Acme lab user used for PAM.

**Infrastructure** (from workspace journal, **operator**-level): same lab
**conventions** as other work — e.g. **Rocky** and **VPS** hosts mentioned for
PAM/portal work may host harness runners; the SDK does **not** require them for
**pure** `msp-add` in Commander.

### 7.2 Planned transcript

- **Path (placeholder date):** `docs/proofs/msp-environment-v1-add-mc-2026-XX-XX.md`
  (or a **json** + **.md** pair consistent with
  [`PAM_PARITY_PROGRAM.md`](./PAM_PARITY_PROGRAM.md) evidence expectations).
- **Contents:** sanitized `dsk` session (or parallel **mock** + **live** split),
  with **`msp-smoke` envelope** (or `msp-info` rows) + **redacted** Commander
  output.

### 7.3 Exit criteria by phase

1. **Schema + validation offline** — `dsk validate` passes on example manifests
   (exit **0** or documented **2** for “no drift” as per [VALIDATION_STAGES.md](./VALIDATION_STAGES.md)).
2. **Mock round-trip** — `plan` / `apply` (mock) matches PAM’s testing depth for
   one op type.
3. **Commander** — one **`create_mc`** in lab tenant, then **re-`plan`** shows
   **no-op**; **destroy** (optional) in line with org policy.
4. **Attestation** — update **`x-keeper-live-proof`** on
  `msp-environment.v1.schema.json` with **`evidence`** path and pin.

**Gate:** [PAM_PARITY_PROGRAM.md](./PAM_PARITY_PROGRAM.md) “PAM bar” **§7
live proof** and matrix row — **not** met until a transcript exists; SDK README
and matrix stay honest per **Q5** and **PAM** documents.

---

## 8. Implementation phase sequence (P0–P7)

Phases are sized to mirror the **split** described in
[`VAULT_L1_DESIGN.md`](./VAULT_L1_DESIGN.md) (models → graph → diff → provider →
validate online) and the **PAM** smoke matrix in
[`PAM_PARITY_PROGRAM.md`](./PAM_PARITY_PROGRAM.md). Counts are **planning
estimates**; a focused team can merge adjacent phases.

| Phase | Description | Files / areas (typical) | Gates | Exit criterion |
|-------|-------------|------------------------|-------|------------------|
| **P0** | **Design freeze + registry hook** — add family key to `schema.py` allow-list (if not already), **no** `dropped-design` for `msp-environment.v1` once product approves. | `keeper_sdk/core/schema.py`, `CHANGELOG.md` | `ruff`, `mypy`, `pytest` subset | `dsk validate` **loads** the future schema (or **feature-flag** rejects with clear error). |
| **P1** | **JSON Schema + Pydantic models** for `msp-environment.v1` (minimal properties). | `keeper_sdk/core/schemas/`, new `manifest_models` or `msp_models.py` | as above + schema tests | Round-trip **YAML** examples from §4. |
| **P2** | **Graph / ordering** — if multiple MCs have dependencies; likely **independent** (parallelisable). | small graph module or reuse patterns from `vault_graph` | as above | Deterministic order for **apply**. |
| **P3** | **Diff** — `compute_msp_diff` (manifest vs `LiveState`), **create/update/delete** op list. | `keeper_sdk/core/…` + tests | as above | Golden vectors from **mock** `managed_companies` fixtures. |
| **P4** | **MockProvider** — `apply` for `create_mc` / (optional) update/delete. | `keeper_sdk/providers/mock.py` + tests | as above | dry-run and apply idempotent. |
| **P5** | **Commander provider** — wrap **`MSPAddCommand`**, then `MSPUpdate` / `MSPRemove` as scope permits; wire `query_enterprise` discover. | `keeper_sdk/providers/commander_*.py` + CLI dispatch | as above + contract tests (argv/kwargs) | One **lab** `create` + **re-plan** clean. |
| **P6** | **`dsk` CLI** — `validate` / `plan` / `diff` / `apply` for the family, exit codes aligned with PAM. | `keeper_sdk/cli/`, `manifest.py` loader **branch** | `pytest -q` full quick suite, **phase0** script if reintroduced | End-to-end **scripted** demo on mock; lab proof optional. |
| **P7** | **Live proof + matrix + `x-keeper-live-proof`**, §7 attestation, **CAPABILITY_MATRIX** row. | `docs/`, `docs/live-proof/` or `docs/proofs/`, schema file | `full` gate if repo has one; maintainer sign-off | [PAM_PARITY_PROGRAM.md](./PAM_PARITY_PROGRAM.md) bar **(1)–(8)** for this family. |

**Estimate:** **4–5** two-week sprints if **P0–P4** and **P5–P6** run back-to-back
with few surprises; **5–6** sprints if **Commander** permission / **interactive
remove** and **RBI+CM** addon rules require extra integration time.

---

## 9. Out-of-scope for this slice (deferred to future MSP slices)

Per §1 and [V2 Q5](./V2_DECISIONS.md#q5--msp-and-epm-in-product-scope):

- **Editing MSP restriction permits** (`msp-info --restriction` data paths).
- **Billing / legacy reports** as declarative — remain **`dsk report`**
  candidates or **Commander**-direct, not this manifest family in slice 1.
- **`msp-convert-node`**, **`msp-copy-role`**, **node conversion** and **role
  cloning** (large Commander surfaces; separate slice).
- **Distributor** and **non-MSP** enterprise flows.
- **EPM / PEDM** — see **Q5** EPM decision; do not block MSP **P0** on EPM.

---

## 10. Open questions

1. **Entity vs `policies`:** Should **MSP-wide defaults** (e.g. echo of **msp
   permits** maxima) live under **`policies:`** or only as **CI validation** sidecars?
2. **Seats in manifest — relative or absolute?** `msp-info` **allocated** is a
   **cap**; is manifest **`seats`** the same, or a **delta** from pool? (Commander
   is **absolute** in `enterprise_registration_by_msp`.)
3. **Does the SDK own pool allocation, or only per-MC existence?** `msp pool` not
   in first slice; confirm product expectation for **out-of-seats** errors on
   **apply**.
4. **`mc` non-interactive remove:** can automation pass **`force=True`**
   safely and still meet **enterprise** audit / confirmation policy?
5. **Rename semantics:** if manifest **name** changes, is that **`update_mc`**
   (`-n` on `msp-update`) or a **new** `create` + `delete` pair?
6. **Addon normalisation in YAML:** `addons` as **string** list (`addon:5`) vs
   structured `{ name, seats }` for schema rigour.
7. **Plan / product_id normalisation in diff:** should live reads always **map
   through** `constants.MSP_PLANS` to a single string before compare?
8. **Ownership / adoption:** does **Managed Company** use `keeper_declarative_manager`
   markers, **separate** enterprise metadata, or **no** marker and **“full MSP
   ownership”** of all MCs in folder (unlikely — clarify with product).
9. **Duplicate names in manifest:** **reject** at validate vs last-write-wins.
10. **Cross-family refs:** PAM on child tenant vs MSP on parent — **out of scope**
   but affects **uid_ref** if future manifests link **PAM** resources to an MC
   (future memo).

### TENTATIVE answers (2026-04-27 — Sprint 7h-57 P0 unblock)

The maintainer chose **option 3** (best-guess defaults so MSP-B P0 can open in
parallel; any answer below is **TENTATIVE — confirm at P0 review**, and a
maintainer override invalidates only the affected P-phase work):

| Q# | Tentative answer | Rationale |
|---|---|---|
| Q1 — entity vs `policies:` | `policies:` block stays **reserved** (not modeled in slice 1). MSP-permits read appears in `params.enterprise` for **CI validation messages** only. | Matches §1 scope fence + §2 schema stub; defers permits modeling without breaking forward compat. |
| Q2 — seats absolute vs relative | **Absolute.** Manifest `seats` is the per-MC cap, identical to Commander `enterprise_registration_by_msp` shape. | Matches Commander semantics; relative-from-pool would require modeling pool state SDK-side (Q3 says no). |
| Q3 — SDK pool allocation | **No.** SDK owns per-MC existence only. Out-of-seats errors surface as `CapabilityError` with `next_action` pointing operator at `msp pool …` (Commander-direct). | Mirrors PAM slice-1 pattern (one verb proven live, then expand); avoids modeling shared mutable global state. |
| Q4 — `force=True` on remove | **Yes** for non-interactive automation, but **gated behind `--allow-delete`** flag (PAM contract parity). | Mirrors PAM `apply --allow-delete` semantics; preserves audit trail via plan. |
| Q5 — rename semantics | **`update_mc`** via Commander `msp-update -n NEW`. **Delete + create** only on UID change (rare; explicit in plan output). | Matches Commander typed verb; preserves MC identity / records / sub-resources across rename. |
| Q6 — addon YAML shape | **Structured** `{ name: <addon-id>, seats: <int> }`. Bare-string shorthand `"addon:5"` rejected at validate. | Schema rigor over typing convenience; matches `keeper-vault.v1` field-shape pattern. |
| Q7 — plan / product_id normalisation | **Yes — always.** Live reads map through `keepercommander.commands.msp.constants.MSP_PLANS` to a single canonical string before compare. | Removes verbose vs non-verbose drift documented in §3 field-mapping table. |
| Q8 — ownership marker | **Reuse `keeper_declarative_manager`** marker family. MC adoption follows the same import / dry-run / commit flow as PAM/vault. | Consistency with two existing families; one ownership story for operators. |
| Q9 — duplicate names in manifest | **Reject** at validate (semantic-rule layer; exit `2`). No last-write-wins. | Matches PAM/vault rules layer; ambiguous manifest is a user error, not a silent merge. |
| Q10 — cross-family refs | **Out of scope** for slice 1 (deferred). Future memo can add `pam-on-mc-tenant.v1` linkage if customer demand fires. | Scope fence per §1; preserves tenant-isolation invariant. |

These defaults set the design surface for Sprint 7h-57 P0 — registry hook in
`schema.py`, scaffold schema JSON, CHANGELOG entry. P1+ phases re-open the
relevant Q answer for confirmation before that phase's gate.

### Document history

| Date | Author | Note |
|------|--------|------|
| 2026-04-27 | SDK maintainers (draft) | Initial memo for Sprint 7h-56 — **msp-environment.v1** slice 1, aligned with [V2 Q5](./V2_DECISIONS.md#q5--msp-and-epm-in-product-scope). |
| 2026-04-27 | SDK maintainers | Sprint 7h-57 P0 unblock — TENTATIVE §10 answers added; option 3 (best-guess + parallel implementation). Maintainer override invalidates only the affected P-phase work. |

### Cross-reference index (required docs)

- [V2_DECISIONS.md — Q5](./V2_DECISIONS.md#q5--msp-and-epm-in-product-scope) — un-drop
  and first-slice **`msp-add-mc` / `msp-environment.v1`**
- [VAULT_L1_DESIGN.md](./VAULT_L1_DESIGN.md) — memo **shape**, scope / live-proof
  tone
- [PAM_PARITY_PROGRAM.md](./PAM_PARITY_PROGRAM.md) — **PAM bar** and phased
  **multi-family** story

(Additional links: [VALIDATION_STAGES.md](./VALIDATION_STAGES.md),
[CONVENTIONS.md](../keeper_sdk/core/schemas/CONVENTIONS.md).)
