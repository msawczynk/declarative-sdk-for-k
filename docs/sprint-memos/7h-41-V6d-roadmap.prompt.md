<!-- Generated from templates/SPRINT_readonly-memo.md, version 2026-04-27 -->

## Sprint 7h-41 V6d — sharing.v1 next-3-sprints roadmap (codex readonly memo)

You are a codex CLI **readonly** worker. Sprint 7h-40 V5a landed `keeper-vault-sharing.v1` typed models + folders diff (offline). Sprint 7h-41 will add sibling block diffs (V6b) + mock provider round-trip (V6a). The orchestrator now needs a **3-sprint roadmap** for closing the family to `supported` status (live-proven), so subsequent sprint planning is grounded.

# Required reading

1. `keeper_sdk/core/schemas/keeper-vault-sharing/keeper-vault-sharing.v1.schema.json` — current `x-keeper-live-proof.status: "scaffold-only"`.
2. `keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json` — for comparison; what does `status: "supported"` require? Cite the evidence chain.
3. `docs/live-proof/keeper-vault.v1.91119c4.sanitized.json` — the canonical live-proof artifact for vault. What lifecycle phases were validated?
4. `scripts/smoke/scenarios.py` — find existing `_vault_one_login_*` functions; vault sibling smoke didn't capture `record_types`/`attachments`/`keeper_fill` yet — does sharing have analogous gaps?
5. `keeper_sdk/providers/commander_cli.py` — search for sharing-related Commander commands. (Commander has `share-record`, `share-folder`, `mkdir -sf`, `mv`, `rmdir`, etc.) Cite the methods that already exist for sharing operations.
6. WORKTREES.md `## Pending decisions` — current open items.
7. `docs/SDK_DA_COMPLETION_PLAN.md` — if it exists, find sharing-related phase descriptions.
8. `docs/V2_DECISIONS.md` — sharing.v1 design decisions.
9. `LESSONS.md` `[capability-census][three-gates]` — the three gates each family must pass before `supported`.

# Deliverable: ~150-line decision memo

## Section 1: Current state audit

Cite each:
- Schema status, evidence path, since_pin (`x-keeper-live-proof` block content).
- Models coverage: which top-level blocks have typed models? (V5a: all 4.)
- Diffs coverage: which blocks have working diff helpers? (Post-V6b: all 4.) Sibling block test counts.
- Provider coverage:
  - Mock: which blocks round-trip? (Post-V6a: folders only; siblings deferred to 7h-42.)
  - Commander CLI: which sharing commands does the provider call today? Search for `share-record`, `share-folder`, `mkdir -sf`. Are there already methods, or scaffold-only?
- Live-proof: zero artifacts yet.

## Section 2: Three-gate analysis

For sharing.v1 to bump `status` from `scaffold-only` to `supported`, what does each gate require?

- **Gate 1 — schema status block annotation**: trivial, just edit the JSON; happens last.
- **Gate 2 — provider slice (mock + commander_cli)**: enumerate the Commander methods needed (e.g. `create_shared_folder`, `share_record_to_user`, `set_shared_folder_default_share`, `delete_shared_folder`, …). Cite each Commander upstream command (use the method name pattern from existing `commander_cli.py` calls).
- **Gate 3 — live-proof transcript**: a `vaultSharingLifecycle` smoke scenario that exercises validate→plan→apply→discover→verify→re-plan→destroy. What's the minimum-viable scenario that exercises all 4 sibling blocks?

## Section 3: 3-sprint slicing recommendation

Propose concrete sprint plans:

### Sprint 7h-42 — provider parity

- V7a: extend `MockProvider` (or new sub-provider) with sibling-block apply (3 blocks). New tests for round-trip.
- V7b: extend `CommanderCliProvider` with sharing methods. Commander CLI commands cited per method. New offline tests with stubbed Commander shell.
- V7c: optional — `dsk` CLI subcommand wiring for `dsk plan/apply` against sharing manifests (or confirm existing dispatch already handles family-aware loading).

### Sprint 7h-43 — smoke scenario design

- V8a: `vaultSharingLifecycle` scenario in `scripts/smoke/scenarios.py`. Manifest fixture (~10 folders, 2 shared_folders, 3 share_records, 4 share_folders covering all subtypes). Verifier that asserts post-apply state.
- V8b: offline tests for the smoke scenario (manifest validates, diff produces expected change shape on mock provider).
- V8c: parallel-guard wiring for sharing scenario lock-key (since shared folder UIDs are tenant-scoped, the per-profile lock prevents collision).

### Sprint 7h-44 — live-proof + supported bump

- V9a (live, codex_live.sh): run `vaultSharingLifecycle` scenario against lab tenant. Capture sanitized transcript at `docs/live-proof/keeper-vault-sharing.v1.<pin>.sanitized.json`.
- V9b: bump schema status to `supported`, update `since_pin` and `evidence`. Add offline meta-test asserting the schema annotation is consistent.
- V9c (readonly): post-mortem memo on sharing.v1 family completion; surface anti-patterns for next family (`keeper-enterprise.v1` is next per V2_DECISIONS).

## Section 4: Resolve PARENT-DECIDE items

For each open ambiguity:
- **Discriminator field for `share_folders` discriminated union**: V5a chose how to dispatch (cite). Validate the choice or recommend a tightening.
- **Subtype switch on share_folder (grantee→record)**: V6b prompt asks the worker to pick CONFLICT vs DELETE+ADD. Confirm the V6b worker's choice is right based on Commander's actual semantics (does Commander support converting a grantee share to a record share in-place, or is it a delete+create?).
- **Default share collision**: how does Commander surface a folder with two default shares? Probably impossible upstream; assert in the diff helper.

## Section 5: Risks + mitigations

- **Commander shell flakiness on sharing commands**: live tenant testing has historically self-fixed bugs (LESSON `[smoke][in-run-self-fix-during-live-proof]` 7h-38). Budget self-fix time in 7h-44 V9a.
- **Sandbox cleanup for sharing**: shared_folder destroy may leave orphan ACLs on records. Cite `scripts/smoke/sandbox.py` cleanup logic; recommend marker-guarded ACL revocation as part of destroy phase.
- **Marker storage on sharing rows**: shared_folders have a `custom` field; record_shares are inherently relational (no record body to mark). Recommend storing markers ONLY on shared_folders + folders; record_shares + share_folders are derived state, marker-guarded by the parent shared_folder's marker.

## Section 6: CANDIDATE LESSON

`2026-04-27 [roadmap][per-family-3-sprint-template] <one-line capturing the audit→provider→smoke→live-proof rhythm>`.

# Constraints

- Read-only.
- Cite file:line for every non-trivial claim.
- Output the full memo as your final response.
- Do not modify any files.
- If any required-reading item is missing or inconsistent with this memo's framing (e.g. mock already supports siblings, or live-proof already exists), FLAG it explicitly and re-baseline.
