# V2 — full-Commander coverage: decision record

This document freezes the answers to the six open questions surfaced by the
2026-04-26 full-Commander-coverage roadmap memo
(`~/.cursor-daybook-sync/codex-prompts/_memos/2026-04-26_dsk-full-commander-coverage.md`).

These decisions unlock phases P9-P18. Revisit only on explicit re-decision.

## Q1 — Schema family naming

**Decision: N small families, one schema file per family, namespaced under
`keeper_sdk/core/schemas/<family>/<family>.v1.schema.json`.**

Rationale (from memo evidence): a single mega-schema would push past the
JSON-Schema mental-budget for plan/diff (vault records alone add ~30+
record types via Commander's `recordv3.py`); per-family files let users
import only what they need and let DSK ship families independently.

Naming + ownership:

| Family | First version | First-class blocks (top-level keys) | Phase |
|---|---|---|---|
| `pam-environment` | `v1` (already shipped) | `projects`, `shared_folders`, `gateways`, `pam_configurations`, `resources`, `users` | P1-P8 |
| `keeper-vault` | `v1` (P9) | `records`, `record_types`, `attachments`, `keeper_fill` | P9 |
| `keeper-vault-sharing` | `v1` (P10) | `folders`, `shared_folders`, `share_records`, `share_folders` | P10 |
| `keeper-enterprise` | `v1` (P11) | `nodes`, `users`, `roles`, `teams`, `enforcements`, `aliases` | P11 |
| `keeper-integrations-identity` | `v1` (P12) | `domains`, `scim_endpoints`, `email_configs` | P12 |
| `keeper-integrations-events` | `v1` (P12) | `automator_endpoints`, `audit_alerts`, `api_keys` | P12 |
| `keeper-ksm` | `v1` (P13) | `ksm_apps`, `ksm_clients`, `ksm_shares` | P13 |
| `keeper-pam-extended` | `v1` (P14) | `gateway_configs`, `rotation_schedules`, `discovery_rules`, `service_mappings`, `saas_mappings` | P14 |
| ~~`keeper-security-posture`~~ | ~~`v1` (P15)~~ — **dropped-design 2026-04-26** | replaced by `dsk report` verbs (Q3) | P15 → Q3 verbs |
| `keeper-epm` | `v1` (P16) | `epm_deployments`, `epm_agents`, `epm_policies`, `epm_collections` | P16 |

Manifests declare `schema: <family>.<version>` at the top — same shape as
existing `pam-environment.v1`. Cross-family references use
`<family>:<key>:<lookup>` form (e.g. `keeper-enterprise:teams:eng-team`)
so a vault-share can target an enterprise-team without bundling them in
one document.

### Q1 amendment — 2026-04-26: P12 `keeper-integrations` → N=2 families

The 2026-04-26 schema-design memo for integrations
(`codex-prompts/_memos/2026-04-26_keeper-integrations-v1-schema-design.md`)
recommended splitting declarative-friendly identity surfaces (domains,
SCIM, outbound email) from one-shot / webhook-heavy surfaces (automator,
audit alerts, API keys). The monolithic `keeper-integrations.v1` scaffold
is **removed**; manifests MUST use `keeper-integrations-identity.v1` and/or
`keeper-integrations-events.v1`. Cross-refs between halves use the same
`family:key:lookup` grammar (e.g. events-side `keeper-vault:records:` for
key material).

### Q1 amendment — 2026-04-26: `keeper-security-posture` dropped-design

The 2026-04-26 schema-design memo for this family
(daybook-sync: `codex-prompts/_memos/2026-04-26_keeper-security-posture-v1-schema-design.md`)
concluded that posture surface (BreachWatch, compliance, security-audit,
weak-password / reused-password / expired-record reports) is intrinsically
read-only and one-shot. A declarative manifest cannot create a breach, and
assertions like "≤0 weak passwords" can't be reconciled idempotently — the
remediation isn't a manifest mutation, it's user action on each flagged
record.

Surface ships as `dsk report` runtime verbs per Q3 instead. The scaffold
file `keeper_sdk/core/schemas/keeper-security-posture/keeper-security-posture.v1.schema.json`
remains in place with `x-keeper-live-proof.status: dropped-design` so any
manifest pinning the family fails validation with the dropped-design status
rather than a confusing "no provider" error. (This required adding
`dropped-design` to the meta-schema enum in
`keeper_sdk/core/schemas/_meta/x-keeper-live-proof.schema.json`.)

Replacement verbs (already enumerated in Q3): `compliance-report`,
`security-audit-report`, `password-report`, `breachwatch-list`,
`record-totp`, `enterprise-reports`.

Un-drop trigger: a customer asks for a posture-as-manifest API AND
Commander grows an idempotent posture-mutation surface. Until both, no
schema work.

## Q2 — Back-compat policy when Commander deprecates a flag DSK relies on

**Decision: 2-version overlap window. When upstream deprecates, DSK keeps
the old behaviour for at least 2 Commander pin bumps (typically ~6-12
weeks) under a `deprecated_in: <commander-sha>` annotation in the matrix.**

Mechanism:

1. `sync_upstream.py --check` flags removed flags as `WARNING (deprecated)` for
   the first pin-bump cycle, `ERROR (removed)` from the third bump onward.
2. Each schema field with a deprecated upstream backing carries
   `"x-keeper-deprecated": {"since-pin": "<sha>", "remove-after-pin": "<sha>",
   "reason": "..."}` in the schema JSON. `dsk validate` emits a warning
   stage-3 message; `dsk plan` emits a comment in the diff.
3. Hard removals require a new schema major (`v2`) + 12-week deprecation
   notice in `CHANGELOG.md` + a `migrate <from> <to>` CLI helper.

Owner: parent decides which removed flag triggers schema major; codex
worker mechanically emits the warnings.

## Q3 — Which runtime-only categories get `dsk` passthrough surface

**Decision: ship `dsk run <commander-cmd>` (single passthrough verb) AND
`dsk report <commander-cmd>` (read-with-redaction verb). NOT a per-command
verb each.**

Two verbs because their semantics differ:

| Verb | Wraps | Output | Redaction | Examples |
|---|---|---|---|---|
| `dsk run` | runtime/session commands that mutate / launch / open | streams to TTY, exit code passed through | minimal — caller asked for it | `connect`, `tunnel start/stop`, `pam launch`, `supershell`, `ssh-agent`, `service start` |
| `dsk report` | read-only commands that emit JSON or report tables | captured, parsed, redacted, printed | full — strip secret fields, mask UIDs in `--quiet` | `aram audit-report`, `compliance-report`, `security-audit-report`, `password-report`, `record-totp`, `enterprise-reports`, `device-management list` |

Out of scope for both: anything in the dropped-design column (msp,
distributor, two_fa enrollment, verify_records, convert) — those need a
product decision before any wrapper ships. `pam_debug` stays out;
debug surfaces are not for end users.

## Q4 — Live-proof per phase or batched at v2.0

**Decision: per-phase, gated by the schema-family declaration.**

Each `<family>.<version>` schema must carry one of:

```jsonc
"x-keeper-live-proof": {
  "status": "supported" | "preview-gated" | "upstream-gap",
  "evidence": "<path to live-proof transcript or 'pending'>",
  "since-pin": "<commander-sha>"
}
```

Rationale: batching at v2.0 means no public release for the entire
duration of P9-P18 (likely 6+ months of work). Per-phase keeps the
release cadence small + makes regressions caught at the phase boundary,
not at v2.0 RC.

Each phase's PR includes a `proof-transcript.md` referenced from the
schema's `evidence` field. Parent owns the live tenant; codex owns the
transcript review against expected JSON.

## Q5 — MSP and EPM in product scope

**Decision:**

- **MSP** → ~~**dropped-design (watch-only).**~~ **In-scope as of 2026-04-27 (Sprint 7h-56).** Un-drop trigger fired:
  - (a) Parent MSP tenant acquired — master admin `msawczyn+msplab@acme-demo.com`, KSM record UID `gu9SvWBHRlPsmRhtjvRX9A`, captured 2026-04-27 in workspace JOURNAL "MSP tenant identity reference (canonical)". Read-only smoke harness `keeper-vault-rbi-pam-testenv/scripts/msp_smoke.py` hardened in Sprint 7h-55 (typed `NotMspLicensed` sub-status, FD-based KSM creds handoff, `tenant_is_msp_licensed` envelope flag, 10/10 unit tests).
  - (b) Customer demand for declarative MSP confirmed by maintainer.
  - First-slice target: **`msp-add-mc`** (add managed company) full lifecycle — validate / plan / diff / apply — under a new schema family **`msp-environment.v1`**. Mirrors `pam-environment.v1`'s first slice scope (one canonical write verb wired end-to-end through the Commander provider) rather than vault.v1's read-many-write-few shape.
  - Design memo: `docs/MSP_FAMILY_DESIGN.md` (Sprint 7h-56 deliverable; drafts schema, manifest examples, diff semantics, `msp-add-mc`/`msp-update-mc`/`msp-remove-mc` provider hooks, live-proof plan).
  - Original un-drop was: "parent acquires an MSP tenant for testing AND a customer asks for declarative MSP. Until both, sync_upstream tracks MSP commands but no schema work."
- **EPM (PEDM)** → **scope kept; P16 stays in the roadmap.** Triggers
  for actual implementation: (a) `pedm_admin.py` source audit lands a
  capability snapshot, (b) at least one EPM customer of DSK exists, (c)
  CI runs a fresh PEDM-licensed tenant smoke. Until all three, P16 is a
  watchlist row only — no schema until audit lands.

The asymmetry: MSP requires a special tenant license that's parent-side
overhead with no current demand; EPM is part of standard enterprise
tenants we already test against, so the audit is cheap and the schema
work has a defensible ROI.

## Q6 — Definition of "all of Commander"

**Decision: 137 statically registered command roots, machine-counted via
the `register_commands` family of functions across the Commander tree.**

This is the unit of coverage P18's extractor maintains. The extractor
counts:

- `keepercommander.commands.base.commands[<name>]` registrations in every
  `register_*_commands` function.
- Nested `GroupCommand` trees expanded one level (so `pam connection edit`
  counts as a leaf, not as `pam connection`).
- External register paths: `keepercommander.importer.commands.register_commands`,
  `keepercommander.plugins.commands.register_commands`,
  `keepercommander.rsync.command.register_commands`,
  `keepercommander.commands.pedm.pedm_admin.register_pedm_commands`,
  `keepercommander.commands.workflow.registry.register_commands`.

Out of count:

- helpers/ + subpackage internals (e.g. `pam/config_helper.py`).
- `start_service` Slack/Teams setup is one root, not multiple.
- alias registrations (`commander.aliases[...]`) are tracked separately
  in the matrix but do not increase the coverage denominator.

`docs/CAPABILITY_MATRIX.md` carries the per-bump count with the canonical
denominator. A coverage cell reads `<supported>/<total>` (e.g. `27/137`)
and the CI drift check fails if the denominator drops without a
matching `--allow-pin-shrink` flag (avoids accidental upstream deletion
masking as coverage progress).

## Out-of-scope

Authentication factor enrollment (`two_fa add/delete`), record format
conversion (`convert`), record repair (`verify_records`), debug
graph/ACL writers (`pam_debug`) remain dropped-design with un-drop
triggers documented in the memo. These are explicit non-goals for v2.0
and beyond.

## Cross-references

- Roadmap memo: `~/.cursor-daybook-sync/codex-prompts/_memos/2026-04-26_dsk-full-commander-coverage.md`
- Prior maintenance-mode memo: `~/.cursor-daybook-sync/codex-prompts/_memos/2026-04-26_dsk-feature-complete-roadmap.md`
- Schema scaffolding: `keeper_sdk/core/schemas/<family>/`
- Live-proof field schema: `keeper_sdk/core/schemas/_meta/x-keeper-live-proof.schema.json`
