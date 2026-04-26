# Master orchestration — run until the program is complete

**Purpose:** One place to answer **(a)** what “done” means, **(b)** what is left,
**(c)** how to **heavily orchestrate** parallel work until exit, without scope
creep. This doc **coordinates** (does not replace):

| Doc | Role |
|-----|------|
| [ORCHESTRATION_PAM_PARITY.md](./ORCHESTRATION_PAM_PARITY.md) | Vault PR train **V0–V8**, gates G0–G6, worker preambles |
| [EXECUTION_PLAN_HEAVY_ORCHESTRATION.md](./EXECUTION_PLAN_HEAVY_ORCHESTRATION.md) | **Phases A–E** time order for vault L1 |
| [NEXT_SPRINT_PARALLEL_ORCHESTRATION.md](./NEXT_SPRINT_PARALLEL_ORCHESTRATION.md) | Wave mechanics, **R/F** packages, tenant serialization, **§16** review |
| [PAM_PARITY_PROGRAM.md](./PAM_PARITY_PROGRAM.md) | PAM bar definition + family inventory |
| [V2_DECISIONS.md](./V2_DECISIONS.md) | Product boundaries (dropped families, MSP, Q3) |
| [V1_GA_CHECKLIST.md](../V1_GA_CHECKLIST.md) | v1.0 tag commitments (orthogonal slices) |

**Daybook (`~/Downloads/JOURNAL.md`):** after each **merge wave** or **tier**
advance, append 5–10 lines (pytest count, active branch, **tier** reached, link
**this file**). Never paste daybook prose into the SDK repo (scope-fence).

---

## 1. Pick your exit tier (binding for the orchestrator)

| Tier | “Done” means | Typical horizon |
|------|----------------|-----------------|
| **A** | **`keeper-vault.v1` + `keeper-vault-sharing.v1`** each pass **G2–G6** for agreed slice-1; README readiness **Yes** for those rows; [`VAULT_L1_DESIGN.md`](./VAULT_L1_DESIGN.md) §7 signed | Weeks–few months |
| **B** | **Tier A** plus every **in-scope** family from [V2 Q1](./V2_DECISIONS.md#q1--schema-family-naming) reaches **G6** **or** has a **one-page ADR defer** (trigger + next review date). **Excludes** `dropped-design`, **Q5-gated** EPM until triggers, MSP until un-drop | Multi-month program |
| **C** | **Tier B** complete + [NEXT_SPRINT §15](./NEXT_SPRINT_PARALLEL_ORCHESTRATION.md) **maintenance mode** active (pin/drift/docs only) | Steady state |

**Default for this master plan:** orchestrate toward **Tier B** unless product
explicitly caps at **Tier A**.

---

## 2. Completion ledger (families × gates)

Copy to a tracking issue or JOURNAL table; integrator ticks cells.

Legend: **✓** done · **◐** in flight · **○** open · **—** N/A (dropped / Q5)

| Family | G0 schema | G1 validate | G2 typed | G3 graph | G4 mock | G5 Commander | G6 proof+matrix |
|--------|:---------:|:-----------:|:--------:|:--------:|:-------:|:--------------:|:---------------:|
| `pam-environment.v1` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (proven paths) |
| `keeper-vault.v1` | ✓ | ✓ | ◐ | ✓ | ✓ | ✓ | ○ |
| `keeper-vault-sharing.v1` | ✓ | ✓ | ○ | ○ | ○ | ○ | ○ |
| `keeper-enterprise.v1` | ✓ | ✓ | ○ | ○ | ○ | ○ | ○ |
| `keeper-integrations-identity.v1` | ✓ | ✓ | ○ | ○ | ○ | ○ | ○ |
| `keeper-integrations-events.v1` | ✓ | ✓ | ○ | ○ | ○ | ○ | ○ |
| `keeper-ksm.v1` | ✓ | ✓ | ○ | ○ | ○ | ○ | ○ |
| `keeper-pam-extended.v1` | ✓ | ✓ | ○ | ○ | ○ | ○ | ○ |
| `keeper-epm.v1` | ✓ | ✓ | — | — | — | — | — (Q5) |
| `keeper-security-posture.v1` | ✓ | ✓ | — | — | — | — | — (dropped) |

**G2 for vault:** `vault_models.py` + `load_vault_manifest` landed; **complete G2**
when design §7 signed **and** any agreed schema tweak (e.g. optional `name`)
is merged or explicitly waived in §7.

---

## 3. Critical paths (after vault L1)

Run **sequentially per family** unless two families have **disjoint**
`CommanderCliProvider` touch paths **and** two integrators — rare.

```text
Vault L1 (V2→V8) ──► Enterprise slices (P11 F2*) ──► Integrations N=2 ──► KSM declarative ──► pam-extended lift stubs
         │                                                                                    ▲
         └────────────────────────── P18c (F1) may advance anytime (does not gate vault) ───┘
```

**EPM (`keeper-epm.v1`):** no G2+ work until [V2 Q5](./V2_DECISIONS.md#q5--msp-and-epm-in-product-scope) triggers — track as **—** in ledger, not “forgotten”.

---

## 4. Orchestration waves (repeat until Tier B)

Each **wave** = one integrator merge window + parallel readonly burst + optional
foreground slices. After **every** wave: **pytest full**, **§16** mini-review
([NEXT_SPRINT](./NEXT_SPRINT_PARALLEL_ORCHESTRATION.md)).

| Step | Action |
|:----:|--------|
| **W.1** | **Cold start:** read §0 of [EXECUTION_PLAN](./EXECUTION_PLAN_HEAVY_ORCHESTRATION.md) + this doc §2 row for active family |
| **W.2** | **Dispatch readonly:** R1/R2/R3/R4 packages not blocked (see [ORCHESTRATION_PAM_PARITY §4](./ORCHESTRATION_PAM_PARITY.md)) |
| **W.3** | **Foreground:** next PR on **critical path** (vault **V2**… or enterprise F2 after vault done) |
| **W.4** | **Live slot** if PR needs tenant: book **one** actor; no parallel writers |
| **W.5** | **Merge + CI**; update **§2 ledger** + JOURNAL |
| **W.6** | **Stop check:** any new doc files this week > 2? If yes, consolidate or defer (anti-bloat) |

**Stop the program** when §1 tier is achieved **or** product files an ADR
capping tier (archive reason in JOURNAL).

---

## 5. Parallelism rules (heavy but safe)

| DO parallelize | DO NOT parallelize |
|----------------|--------------------|
| Readonly memos R* on disjoint topics | Two PRs touching same `commander_cli.py` region |
| P11 schema **different** `$defs` files | Two agents on **same** lab tenant write path |
| P18c F1 while vault V2–V4 in flight | Vault **V5/V6** + unrelated Commander refactor |
| Tests colocated with each feature PR | Skipping full pytest before merge “to save time” |

---

## 6. Heavy metrics (integrator dashboard)

| Metric | Target | Breach action |
|--------|--------|---------------|
| `main` green | Always between merges | Revert or fix-forward same day |
| Open PRs touching `commander_cli.py` | ≤ 1 | Queue extras |
| New `docs/*.md` per calendar week | ≤ 2 unless approved | Fold into existing doc |
| Ledger rows stuck **◐** > 14 days | 0 | Blocker template ([ORCHESTRATION_PAM_PARITY §8](./ORCHESTRATION_PAM_PARITY.md)) |
| JOURNAL SDK snapshot age | ≤ 7 days while active | Update in Phase 0.4 |

---

## 7. Remaining work checklist (actionable)

### Vault (Tier A anchor)

- [ ] Sign [`VAULT_L1_DESIGN.md`](./VAULT_L1_DESIGN.md) §7 (removes **DRAFT**)
- [x] **V2** graph for vault `uid_ref` / `folder_ref` (+ tests) — `vault_graph.py`
- [x] **V3** mock discover / diff / plan — `compute_vault_diff` + `MockProvider`;
  `tests/test_vault_mock_provider.py`
- [x] **V4** CLI / loader dispatch — `load_declarative_manifest` + plan/diff/apply
- [x] **V5–V6** Commander discover + apply (slice-1 **login**; mocked + unit tests;
  live L1 proof still **V8**)
- [x] **`dsk validate --online`** for vault (Commander `discover` + `compute_vault_diff` smoke;
  requires `--provider commander` + folder scope)
- [ ] **L1** live proof transcript + **V8** schema + matrix + README
- [x] **Publish:** `main` pushed to `origin`; confirm GitHub **CI green** on the head SHA after each merge wave (re-check whenever `main` is ahead again)
- [x] **Hardening (post-UPDATE):** assert Commander **vault UPDATE** success (no silent
  `RecordEditCommand` no-op) via `return_result["update_record_v3"]` when body still changes
- [x] **Hardening (docs):** semantic **login** diff limits, concurrent-edit + CI split for
  `vault_online` in [`VAULT_L1_DESIGN.md`](./VAULT_L1_DESIGN.md) §4 and [`VALIDATION_STAGES.md`](./VALIDATION_STAGES.md)
- [ ] **Concurrency:** call out in §7 / `VAULT_L1_DESIGN` — `validate --online` is a point-in-time
  snapshot; concurrent mobile/admin edits can invalidate assumptions before `apply`

### Program infrastructure

- [ ] **P18c** (F1): JSON allowlist + stable snapshot buckets ([R1](./P18_SYNC_UPSTREAM_EXTRACTOR_DECISION.md))
- [ ] **P11** (F2a/F2b): schema slices after memos
- [ ] **Optional** fourth `dsk report` verb (F4 after R3 memo only)

### Tier B — per additional family (template)

For each family row still **○** in §2: repeat **V1-like** train (design memo →
models → graph → mock → Commander → proof) **or** file **ADR-defer** with
un-drop triggers and stop editing that family until triggers fire.

### Closeout

- [ ] [NEXT_SPRINT §16](./NEXT_SPRINT_PARALLEL_ORCHESTRATION.md) full sprint review
- [ ] README hero update **only** if Tier B achieved for chosen scope
- [ ] Archive / freeze this doc with final date in **revision log** (§9 below)

---

## 8. “Continue” one-liner for agents

```text
Read docs/ORCHESTRATION_UNTIL_COMPLETE.md §1 tier + §2 ledger; execute the next
unchecked §7 item for the active family; cite ORCHESTRATION_PAM_PARITY PR-Vx;
full pytest before handoff; update JOURNAL snapshot not repo daybook.
```

---

## 9. Revision log (integrator fills)

| Date | Note |
|------|------|
| 2026-04-26 | Initial master plan; vault G2 partial (`vault_models.py`). |
| 2026-04-26 | Vault G3 partial: `build_vault_graph` + `vault_record_apply_order` (`vault_graph.py`). |
| 2026-04-26 | Vault G4 partial: `compute_vault_diff` + mock round-trip (`vault_diff.py`, `test_vault_mock_provider.py`). |
| 2026-04-26 | Vault G5 partial: `load_declarative_manifest` + CLI plan/diff/apply + validate JSON (`manifest.py`, `cli/main.py`). |
| 2026-04-26 | Vault Commander slice: `CommanderCliProvider` discover filter + `_apply_vault_plan` / `RecordAddCommand` (`commander_cli.py`). |
| 2026-04-27 | §10 next-wave table + vault `validate --online` (`cli/main.py`); §7 checklist tick. |
| 2026-04-27 | Doc reconcile: `VALIDATION_STAGES`, `PAM_PARITY_PROGRAM`, `README`, `AGENTS`, `VAULT_L1_DESIGN` §8, `live-proof/README`, vault schema `x-keeper-live-proof.notes` (no status bump). |
| 2026-04-27 | Vault Commander **UPDATE** applies manifest drift (`RecordEditCommand`) before marker refresh; `_vault_merge_custom_for_update` preserves SDK marker in `custom[]`. |
| 2026-04-27 | Vault UPDATE: restrict body sync to **record version 3** (Commander `RecordEditCommand`); unit tests for `_vault_patch_login_record_data`. |
| 2026-04-27 | `compute_vault_diff` semantic **login** compare (manifest `fields[]` vs flattened live); `tests/test_vault_diff.py`. |
| 2026-04-27 | Vault diff: case-label regression test; `AGENTS` / `VALIDATION_STAGES` / README / `vaultMinimal.yaml` note semantic `plan`/`diff`. |
| 2026-04-27 | §2 ledger: `keeper-vault.v1` G3–G5 → ✓; `docs/live-proof` V8 template JSON + README; CI validates `docs/live-proof/*.json`. |
| 2026-04-27 | `docs/SCAFFOLD.md` live-proof row; `tests/test_live_proof_artifacts.py`; `PAM_PARITY_PROGRAM` vault inventory line. |
| 2026-04-27 | `examples/scaffold_only/vaultOneLogin.yaml` L1 sample; live-proof + PAM parity V8 cross-links; `test_validate_json_scaffold_vault_one_login`. |
| 2026-04-27 | Plan + README: §7 checklist adds publish, post-UPDATE hardening, concurrency; §10 wave table retargets hardening + devil’s-advocate block; README fixes `--online` scope, adds honest vault limits, bumps status + test count. |
| 2026-04-27 | Vault UPDATE: `RecordEditCommand` `return_result` guard + no-op skip when merged == existing (`commander_cli.py`); §7/§10 hardening rows split code vs docs. |
| 2026-04-27 | Doc hardening: `VAULT_L1_DESIGN` §4 semantic diff + races + UPDATE guard; `VALIDATION_STAGES` vault caveats + remediation rows; §7 docs checkbox closed. |
| 2026-04-27 | §7 publish item: routine push + CI check on head SHA (merge-wave hygiene). |
| 2026-04-27 | `AGENTS.md`: vault L1 semantic-diff + race pointer after `VALIDATION_STAGES` link. |
| 2026-04-27 | `docs/SCAFFOLD.md` + `keeper_sdk/providers/SCAFFOLD.md`: vault doc index + Commander row / Vault L1 caveat links. |
| 2026-04-27 | `ORCHESTRATION_PAM_PARITY` §1 gate table + V6 row reconciled; `live-proof/README` + README layout vault pointers. |
| 2026-04-27 | `PAM_PARITY_PROGRAM` inventory + Phase 0/1a validate modes; `EXECUTION_PLAN` Phase D V6 + L1/V8 exit criteria. |
| 2026-04-27 | `ORCHESTRATION_PAM_PARITY` §3: status pointer (§1 + ledger authoritative; train table historical). `CHANGELOG` Unreleased **Changed** split into bullets. |
| 2026-04-27 | `V1_GA_CHECKLIST` §5 vault `validate --online` footnote; `EXECUTION_PLAN` Phase A exit pointer post–V0–V6. |
| 2026-04-27 | `examples/SCAFFOLD.md`: CI validate vs plan loop, `vaultOneLogin`; `NEXT_SPRINT` hub link → §7. |
| 2026-04-27 | `ORCHESTRATION_PAM_PARITY` §7 CI ladder reconciled to `ci.yml` + pytest; README layout `examples/SCAFFOLD.md`. |

---

## 10. Next orchestration wave (post V5–V6 land)

**Binding tier until product says otherwise:** **Tier A** (vault + vault-sharing slice-1).

**Devil’s-advocate reminder (integrator reads before ticking G6):** semantic vault
login diff matches **scalar** flattening — not a proof of unique field slots or
cross-Commander-version payload stability; **UPDATE** is **record v3** JSON only;
`validate --online` bundles I/O + diff and can flake independently of schema-only
CI; JSON modes need redaction discipline. README § “Honest limits” mirrors this.

| Lane | Owner | Next deliverable | Parallel OK? |
|------|-------|------------------|--------------|
| **Vault G6 / V8** | Integrator + one live slot | Sanitized transcript per `docs/live-proof/README.md`; bump `x-keeper-live-proof` on `keeper-vault.v1`; matrix + README row | **No** parallel tenant writers |
| **§7 sign-off** | Integrator + reviewer | Close **G2** ledger row (removes `DRAFT` on `VAULT_L1_DESIGN.md`) | Readonly review only |
| **Vault hardening** | Foreground dev | **Code:** `return_result` guard (**done**). **Docs:** §4 + validation caveats (**done**); extend only if L1.1 / new Commander shapes need more | **No** second PR touching same `commander_cli.py` region without queue |
| **P18c F1** | Worker / Codex | R1 memo + extractor allowlist (does **not** gate vault) | **Yes** |
| **P11 F2** | Worker | Memos first; schema edits after integrator merge | **Yes** if disjoint `$defs` |
| **Wave close** | Integrator | W.5 merge + full pytest + **NEXT_SPRINT §16** skim; JOURNAL 5-line snapshot | — |

**W.6 this week:** avoid new top-level `docs/*.md` unless consolidating; prefer edits to this file + `ORCHESTRATION_PAM_PARITY.md`.
