# Devil's-Advocate SDK Completion Plan

Date: 2026-04-25

Purpose: finish `declarative-sdk-for-k` without turning unproven Keeper behavior
into support claims. This plan supersedes optimistic feature-count roadmaps when
there is a conflict. The SDK is "complete" only when every modeled capability is
one of:

- `supported`: unit tests + docs + live proof + clean re-plan.
- `preview-gated`: schema/model surface exists, but support is not claimed.
- `upstream-gap`: pinned upstream lacks a safe writer/readback path.

## Current Truth

Shipped and proven:

- Core declarative lifecycle: validate -> plan -> apply.
- Ownership markers, adoption guardrails, delete gating.
- Commander-backed GA PAM lifecycle for non-preview manifests.
- `EnvLoginHelper` full `pamMachine` create -> verify -> clean re-plan ->
  destroy live proof.
- **KSM / `KsmLoginHelper`:** 2026-04-28 COMPLETE: `pamMachine` smoke PASSED
  end-to-end with `--login-helper profile`. Profile setup:
  `~/.config/dsk/profiles/default.json` + `~/.keeper/ksm-config.json`. Testuser2
  reuse path from admin vault record — no re-enrollment needed. 2026-04-29
  bootstrap smoke also live-proven: `tests/live/test_ksm_bootstrap_smoke.py`
  exit **0** (1 passed), with create/bind/share, config redemption, login probe,
  and transcript leak check clean.
- Provider capability gaps surface as plan conflicts; `validate --online` now
  fails on provider capability gaps.
- **`keeper-vault.v1` L1 (`login` slice + typed custom fields): `supported`** —
  2026-04-28 live proof (`vaultOneLogin` smoke PASSED create→verify→destroy);
  2026-04-29 offline broadening adds typed `url` / `email` / `phone` /
  `address` / `secret_question` / `multiline` field validation, type-aware diff,
  free-form `custom[]` key/value rows, and redacted `file_ref` stubs. Binary
  file upload remains an upstream-gap until upload policy lands.
- **MSP discover / `msp-environment.v1`:** 2026-04-28 live proof:
  `dsk validate --online` + `dsk plan` exit 0 against lab tenant using
  `tests/fixtures/examples/msp/01-minimal-msp.yaml`. Read-only discover + plan
  path confirmed. W10 classifies MSP managed-company writes as
  **design-complete / preview-gated**: Commander exposes `msp-add`,
  `msp-update`, and `msp-remove`, and offline wrappers/tests exist, but public
  support remains discover/validate/plan/diff only until a Commander
  adoption-marker contract and MSP admin live proof land. Commander `dsk import`
  still fails capability because no marker writer is proven.
- **CommanderServiceProvider:** `supported` offline mock for Commander Service
  Mode REST API v2 transport. It submits async commands, polls status, fetches
  results, supports FILEDATA for `pam project import --filename=FILEDATA`, and
  reuses CommanderCliProvider capability gaps. No live Service Mode proof is
  claimed yet.
- **`keeper-epm.v1` offline foundation:** W18 adds schema, typed model load,
  and field-level diff for Endpoint Privilege Management watchlists, policies,
  approvers, and audit_config. Offline validation is supported. Plan/apply are
  `upstream-gap` until a PEDM-licensed tenant writer/readback path is proven;
  the planned lab path is MSP managed company context with augenblik.eu test
  users.
- **`keeper-ksm.v1` mock lifecycle:** W6b supports offline mock
  `plan`/`apply` for apps, tokens, record shares, and config outputs with
  ownership markers and clean re-plan. Commander apply remains preview-gated.
- **CLI export / manifest lift (`dsk export`):** 2026-04-29 live proof:
  Commander-shaped PAM project JSON → `dsk export` → `dsk validate` exit **0**
  (`ok: dsk-export-test (2 uid_refs)`). Commander 17.2.16 has no native
  `pam project export`; the SDK reads a JSON file produced by the supported
  helper/export path.
- **Vault/plan drift view (`dsk diff`):** 2026-04-29 live proof vs lab tenant:
  exit **2** when changes present (informational exit contract); renderer/path
  accepted live.
- **Operator reports (`dsk report password-report`):** 2026-04-29 live proof:
  exit **0**, 11-row output envelope, **`--sanitize-uids`** run clean (no UID
  leak signal). Redaction/leak-contract surface accepted for guarded reporting
  use.
- **Operator reports (`dsk report security-audit-report`):** 2026-04-29 live
  proof: `--sanitize-uids --quiet` exit **0**, JSON output envelope emitted, and
  first safe output line was `{`.
- **Operator reports (`dsk report compliance-report`):** 2026-04-29 live attempt:
  requested `--sanitize-uids --quiet` path hit the Commander empty-cache
  stdout/error shape; `--rebuild` probe emitted the expected JSON envelope.
  The SDK wrapper now retries no-rebuild empty stdout, empty JSON, or Commander
  error output with `--rebuild`, strips rebuild stdout artifacts, and emits the
  normal redacted JSON envelope.
- **DSK MCP server:** stdio JSON-RPC server exposes declarative lifecycle tools
  for AI agents. Offline mode uses `MockProvider`; service mode is gated by
  `KEEPER_SERVICE_URL` + `KEEPER_SERVICE_API_KEY`.

**Acceptance (export / diff / password-report / security-audit-report /
compliance-report)** — satisfied 2026-04-29 on lab tenant plus offline
empty-cache wrapper coverage (see bullets above).

Recently unblocked:

- Nested `resources[].users[].rotation_settings`: **readback-supported,
  apply live-blocked** for Commander 17.2.16+. GH#35 added `pam rotation list
  --record-uid --format json`; SDK discover now hydrates nested
  `pamUser.rotation_settings` from that JSON so post-apply re-plan can compare
  real Commander state instead of relying on missing-readback suppression.
  2026-04-29 W1 live smoke reached `pam rotation edit`, then Keeper router
  returned `Set rotation error "500": Internal server error`; the harness
  cleaned up with no SDK-owned records left in the sandbox shared folder.
  Until a create -> clean re-plan -> destroy transcript passes, do not claim
  nested rotation apply support. Top-level `users[].rotation_settings` remains
  outside this lift.

Not yet supported:
- Post-import RBI fields outside the P3.1 supported buckets: URL, DAG
  tri-states, and proven typed booleans are supported / import-supported per
  `docs/COMMANDER.md` and `docs/RBI_READBACK_DESIGN.md`; list-shaped,
  audio-only, RBI text recording, and unproven credential/key-event rows stay
  explicitly out of supported claims.
- Standalone top-level `pamUser`.
- JIT writes (`upstream-gap` confirmed by `docs/JIT_DESIGN.md`).
- Gateway `mode: create` and top-level `projects[]`.
- Broader non-PAM Keeper surface beyond the current documented boundaries.

## Completion Gates

No feature may move from `preview-gated` to `supported` unless all gates pass:

1. The provider can apply the capability without direct DAG writes.
2. Dry-run or plan output shows the exact intended mutation.
3. Apply writes no secrets to stdout/stderr/log artifacts.
4. Re-discovery sees enough state to produce a clean re-plan.
5. Destroy/cleanup removes only SDK-owned resources and leaves the tenant clean.
6. Docs, examples, scaffold, and changelog match the actual support claim.
7. A reviewed live smoke proves the exact supported path.

Devil's advocate default: if any gate is ambiguous, keep the feature
`preview-gated`.

## Phase 0: Stabilize Current Branch

Goal: make the current dirty tree reviewable before more feature work.

Tasks:

1. Split review into coherent PR units if needed:
   - Commander provider rotation/discover fixes,
   - smoke scenario/docs,
   - validation/docs hardening.
2. Re-run focused checks:
   - `python3 -m pytest -q tests/test_cli.py tests/test_commander_cli.py tests/test_smoke_scenarios.py tests/test_smoke_args.py`
   - `python3 -m ruff check keeper_sdk/cli/main.py keeper_sdk/providers/commander_cli.py tests/test_cli.py tests/test_commander_cli.py`
   - GitHub YAML parse.
3. Run full integration checks before merge:
   - `python3 -m pytest -q`
   - `python3 -m ruff check .`
   - `python3 -m ruff format --check .`
   - `python3 -m mypy keeper_sdk`
   - `python3 -m build && python3 -m twine check dist/*`
4. Update `CHANGELOG.md` for changed behavior and known preview blockers.

Acceptance:

- Full local checks green.
- Dirty tree can be explained by PR scope.
- No new support claim is made for rotation or RBI.

## Phase 1: Publish / Release Hygiene

Why first: packaging failures hide SDK breakage from downstream users.

Distribution is **GitHub only** (no PyPI). Tasks:

1. Ensure `.github/workflows/publish.yml` builds `dist/*` and uploads assets to
   each **GitHub Release** (`gh release upload`).
2. On each new tag/release, confirm the workflow is green and wheels/sdist are
   attached to the release page.
3. Install smoke from **git URL or wheel** in a clean venv:
   - `dsk --help`
   - `dsk validate examples/pamMachine.yaml`
   - `dsk --provider mock plan examples/pamMachine.yaml --json`

Devil's advocate:

- Do not claim PyPI install; it is out of scope for this repo.
- Do not cut a release without verifying `twine check` in CI and attachable
  artifacts.

Acceptance:

- `docs/RELEASING.md` and `README.md` install instructions match GitHub-only
  reality.

## Phase 2: Finish Rotation Honestly

2026-04-29 update: Commander GH#35 is resolved in 17.2.16 with
`pam rotation list --record-uid --format json`; the SDK now wires that readback
into `discover()` for nested `pamUser.rotation_settings`. W1 live smoke proved
auth, sandbox, validate, initial plan, and entry into `pam rotation edit`, but
the router returned `Set rotation error "500": Internal server error` during
apply. Treat nested rotation as readback-supported but apply live-blocked until
the committed smoke passes end to end.

### P2.1 Diagnose Rotation Drift

**Status:** 2026-04-29 readback-supported / apply live-blocked for nested
`resources[].users[].rotation_settings` on Commander 17.2.16+. The former
readback blocker was GH#35 (`pam rotation list` lacked UID filtering + JSON
output); Commander 17.2.16 unblocks the read path. W1 apply proof is blocked by
Keeper router 500 from `pam rotation edit`.

Questions:

- Which fields differ on post-apply `pamUser`?
- Which fields differ on post-apply containing `pamMachine`?
- Are these actual missing writes, readback-shape gaps, or SDK-only placement
  metadata that should be ignored?
- Does `pam rotation edit` persist rotation in a Commander-readable surface, or
  only in a DAG/router surface the current `discover()` does not read?

Tasks:

1. Add an offline fixture reproducing post-apply live payload shape for nested
   `pamUser` + containing `pamMachine`.
2. Make drift output structured enough to identify exact field names in live
   smoke failure tails. Offline anchor:
   `tests/test_diff.py::test_diff_nested_pam_user_rotation_drift_surfaces_rotation_settings_key`
   (nested ``pamUser`` ``rotation_settings`` shows up on ``compute_diff`` UPDATE rows).
3. If fields are SDK-only linkage metadata, add them to the ignored drift set
   with a focused regression test.
4. If fields are real rotation settings, design readback before any gate lift.
   Readback is now implemented through `pam rotation list --record-uid --format
   json`; apply support still needs a passing live smoke because W1 hit Keeper
   router 500 while setting rotation.
5. Fix smoke cleanup if the managed Resources folder UID becomes stale after
   failed re-plan; cleanup must resolve by project name as fallback.

Focused tests:

- `tests/test_commander_cli.py`
- `tests/test_smoke_scenarios.py`
- `tests/test_cli.py` if exit behavior changes.

Live proof:

```bash
python3 scripts/smoke/smoke.py --login-helper env --scenario pamUserNestedRotation
```

Acceptance:

- Apply OK.
- Marker verification OK.
- Post-apply re-plan exits 0.
- Destroy plan shows deletes.
- Destroy apply OK.
- Final discover shows no SDK-owned records.

Gate-lift rule:

- Only nested `resources[].users[].rotation_settings` readback is ungated for
  Commander 17.2.16+.
- Nested rotation apply support stays blocked until the committed
  `pamUserNestedRotation` smoke passes create -> clean re-plan -> destroy.
- Top-level `users[].rotation_settings` stays blocked.
- `default_rotation_schedule` stays blocked unless a separate setter/readback
  proof exists.

## Phase 3: Finish Post-Import Tuning / RBI

**2026-04-29 update:** E2E `pamRemoteBrowser` live smoke and
`docs/live-proof/*rbi*` on `main` **passed**; `docs/COMMANDER.md` has P3.1
buckets and `docs/RBI_READBACK_DESIGN.md` is now the authoritative per-field
gate decision. URL from `rbiUrl`, DAG `allowedSettings` -> `pam_settings.options`
tri-states, and the typed booleans proven by the smoke are supported. The
remaining 10 risk fields are classified: `autofill_credentials_uid_ref` and
`recording_include_keys` stay `preview-gated`; list-shaped controls, RBI text
recording, and audio controls stay `upstream-gap`.

Issue #5 closeout evidence: smoke rc=0 (`pamRemoteBrowser` create -> verify ->
clean re-plan -> destroy), committed sanitized artifact
`docs/live-proof/keeper-pam-environment.v1.89047920.rbi.sanitized.json`,
COMMANDER P3.1 table buckets, and `docs/RBI_READBACK_DESIGN.md`.

Ongoing risk: Commander still **writes** some RBI tri-states to DAG
`allowedSettings` first; the SDK does **not** re-read the DAG in subprocess-only
`discover()` (no in-process `KeeperParams`). The in-process merge is
best-effort when the session and graph are present.

### P3.1 Split Tuning Claims

Classify each field as one of:

- `import-supported`: Commander import/extend owns it and discover reads it.
- `edit-supported-clean`: post-import edit writes it and discover reads it.
- `edit-supported-dirty`: post-import edit writes it but discover cannot read it.
- `upstream-gap`: no safe writer or no safe readback.

Tasks:

1. Keep `docs/COMMANDER.md` P3.1 classifications aligned with the field map.
2. Add tests when a dirty/upstream-gap field moves into a supported bucket.
3. Track the 10 remaining risk fields from `docs/RBI_READBACK_DESIGN.md` as
   explicit non-support until their writer/readback proof lands.
4. Do not bundle connection fields with RBI fields if their readback behavior
   differs.

### P3.2 Readback Design

Options to evaluate:

- Extend `discover()` to read the relevant Commander/DAG surface through
  Commander APIs only.
- Treat DAG-only RBI fields as apply-only preview with no supported re-plan
  claim.
- Split RBI support into import/read fields now and DAG-backed toggles later.

Devil's advocate:

- Direct DAG reads may be lower risk than DAG writes, but they still couple the
  SDK to internal state shape. Require source-cited design before code.
- If clean re-plan cannot be proven, do not remove preview gates.

Acceptance:

- `pamRemoteBrowser` live smoke (2026-04-28) **passes** end-to-end; fields
  claimed as **supported** must match `docs/COMMANDER.md` P3.1 rows,
  `docs/RBI_READBACK_DESIGN.md`, and `test_rbi_readback.py` (and smoke where
  applicable). Fields listed as `preview-gated` or `upstream-gap` in the design
  doc stay out of `supported` table rows in the product matrix.
- Maintainer closeout checklist for GitHub #5: cite the sanitized RBI artifact,
  `COMMANDER.md` P3.1 table, `SDK_DA_COMPLETION_PLAN.md` Phase 3 acceptance,
  `docs/RBI_READBACK_DESIGN.md`, and
  `bash scripts/phase_harness/run_local_gates.sh`; do not paste raw logs or
  credentialed transcript paths.

## Phase 4: Close Deferred v1 Quality Gaps

Purpose: make "complete" mean robust, not just feature-rich.

Tasks:

1. Resolve remaining `xfail`s only when behavior exists:
   - Commander version mismatch gate — **offline done** (`apply_plan` reads
     `importlib.metadata.version("keepercommander")`; test
     `test_apply_rejects_keepercommander_below_minimum`).
   - Partial-apply rollback/reporting — **offline done** (`partial_outcomes` on
     `CapabilityError` + per-row `apply_failed` details; test
     `test_apply_partial_failure_records_outcomes_then_raises`).
2. Add duplicate-title and duplicate-config checks where live lookups use names.
3. Add two-writer race coverage:
   - plan clean,
   - marker changes before apply,
   - apply refuses or reports conflict without mutating unrelated records.
4. Clarify CLI dry-run semantics:
   - CLI `apply --dry-run` is plan-equivalent.
   - Provider `apply_plan(dry_run=True)` may expose provider preview details for
     SDK callers.

Acceptance:

- [x] Add two-writer race coverage (`tests/test_two_writer.py` — 3 cases, 982
  pass under the local gate run).
- [x] Add field-drift UPDATE smoke (`tests/test_vault_update_smoke.py`).
- [x] Add adoption lifecycle smoke (`tests/test_adoption_smoke.py`).
- `tests/test_dor_scenarios.py` has no stale expected deferrals.
- CLI docs match actual dry-run behavior.
- Race conditions fail closed.

## Phase 5: JIT Boundary

Current classification: `upstream-gap` confirmed by `docs/JIT_DESIGN.md` on
2026-04-29.

Tasks:

1. Re-check pinned Commander source before each release that might include JIT.
2. If a safe writer exists:
   - build pure mapping helper,
   - keep preview gate,
   - add mocked tests,
   - require live smoke.
3. If no safe writer exists:
   - keep `jit_settings` preview-gated,
   - update issue with source refs and `docs/JIT_DESIGN.md`,
   - do not add apply shims.
4. Close GitHub #6 as `upstream-gap` unless Commander exposes `pam jit` or an
   equivalent safe writer/readback surface.

Acceptance:

- JIT is either source-backed `supported` or explicitly `upstream-gap`.
- No direct DAG writes.

## Phase 6: Gateway Create / Projects

Current classification: design-only / `preview-gated`.

Tasks:

1. Harden provider conflict for top-level `projects[]` when `DSK_PREVIEW=1`.
2. Decide whether gateway create is:
   - SDK-owned provisioning, or
   - operator-scaffolded next action followed by `reference_existing`.
3. Define multi-project semantics:
   - exit aggregation,
   - partial failure boundaries,
   - cleanup behavior,
   - folder/gateway isolation.

Devil's advocate:

- Gateway create likely involves local infrastructure and long-running side
  effects. Do not hide that behind a declarative "apply" row until teardown and
  rollback are understood.

Acceptance:

- Design doc says exactly what is supported now, later, or never.
- No gate lift without disposable live proof.

## Phase 7: Broader Keeper Surface

Do not hand-code broad support from memory. Mirror upstream first.

Status (2026-04-29, v1.3.0):

| Surface | Classification | Evidence | Remaining bar |
|---------|----------------|----------|---------------|
| Shared-folder validate / sharing lifecycle | `preview-gated` | Offline validation covers the manifest surface; P35 mock lifecycle proves shared-folder member create/delete/update planning plus mocked Commander share call without a second Keeper account. P34 adds offline Commander membership-removal `--allow-delete` guard proof. | Live membership proof is blocked pending a second Keeper account; keep support preview-gated until that create -> re-plan -> delete path is live-proven. |
| Shared-folder Commander write primitives | `supported` for create/update/membership command wiring; not full lifecycle support | P30/P34 provider tests cover create/update, membership grant/remove, permission breadth, and destructive-change `--allow-delete` guards. | Full shared-folder lifecycle support still needs second-account live readback proof. |
| KSM application `reference_existing` | `supported` for gateway read/validate only | Gateway read path is proven for existing app references. | No SDK-owned app mutation is implied by this support claim. |
| KSM application create | `supported` for `bootstrap-ksm`; `keeper-ksm.v1` mock/offline lifecycle `supported`; Commander apply `preview-gated` | 2026-04-29 live proof: `tests/live/test_ksm_bootstrap_smoke.py` exit 0 (1 passed); bootstrap create/bind/share, config redemption, login probe, and transcript leak check were clean. W6a adds schema, typed loader, graph, field-level diff, and offline tests for apps, tokens, record shares, and config outputs. W6b adds `KsmMockProvider`, mock `plan`/`apply`, ownership markers, dry-run no-write behavior, and clean re-plan tests. | Needs Commander/KSM discovery/apply write/readback, ownership marker persistence, clean re-plan, and cleanup proof before claiming live declarative KSM lifecycle support. |
| KSM inter-agent bus | `preview-gated` (offline mock) | `keeper_sdk/secrets/bus.py` implements JSON custom-field envelopes, `VersionConflict` CAS checks, polling subscribe, delete, and `BusClient` channel send/receive/ack/gc. Offline proof: `tests/test_ksm_bus_impl.py` covers create, CAS conflict, subscribe-on-change, delete, ordering, recipient filtering, channel separation, cursors, and TTL GC. | Live proof still required before a support claim: run sanctioned KSM bus write/readback and concurrent-writer characterization through the committed live harness; KSM SDK conditional-write semantics remain undocumented. |
| `keeper-enterprise.v1` offline foundation | `supported` offline for schema + typed load + graph + diff/plan rows; `preview-gated` for live/provider claims | P11 adds full offline schema coverage for `nodes`, `users`, `roles`, `teams`, `enforcements`, and `aliases`, plus typed models, dependency graph, field-level diff, plan ordering, and 15+ offline tests in `tests/test_enterprise_schema.py`. Existing PAM manifests still reject unknown team/role resource types. | `dsk validate --online`, discovery, import/apply, ownership markers, and clean live re-plan remain future/upstream-gap until Commander enterprise read/write contracts are proven. |
| `keeper-integrations-identity.v1` offline foundation | `supported` offline for schema + typed load + diff rows; `upstream-gap` for apply | W14 adds offline schema coverage for domains, SCIM provisioning, SSO providers, and outbound email, plus typed models, field-level diff, and 15+ offline tests in `tests/test_integrations_identity.py`. | `dsk validate` stays schema-only; `dsk plan` / apply exit capability until a safe Commander write/readback API is confirmed. |
| `keeper-integrations-events.v1` offline foundation | `supported` offline for schema + typed load + diff rows; `upstream-gap` for apply | W15 adds offline schema coverage for automator rules, audit alerts, API keys, and event routes, plus typed models, field-level diff, and 15+ offline tests in `tests/test_integrations_events.py`. | `dsk validate` stays schema-only; `dsk plan` / apply exit capability until a safe Commander write/readback API is confirmed. |
| `keeper-pam-extended.v1` offline foundation | `supported` offline for schema + typed load + diff rows; `preview-gated` for apply | W17 adds offline schema coverage for gateway configs, rotation schedules, discovery rules, and service mappings, plus typed models, field-level diff, and 15+ offline tests in `tests/test_pam_extended.py`. | `dsk validate` stays schema-only; `dsk plan` / apply exit capability until a safe Commander write/readback API is live-proven. |
| `keeper-epm.v1` offline foundation | `supported` offline for schema + typed load + diff rows; `upstream-gap` for apply | W18 adds offline schema coverage for EPM watchlists, elevation policies, approvers, and audit_config, plus typed models, field-level diff, and 15+ offline tests in `tests/test_epm_schema.py`. | `dsk validate` stays schema-only; `dsk plan` / apply exit capability until PEDM tenant writer/readback support is proven through the MSP managed company lab path with augenblik.eu test users. |
| Compliance/security-audit reports | `supported` | 2026-04-29 `security-audit-report --sanitize-uids --quiet` live proof exited 0 with a JSON envelope. `compliance-report --sanitize-uids --quiet` hit Commander empty/non-JSON cache output; `--rebuild` emitted the expected envelope, and the SDK wrapper now auto-retries no-rebuild empty/error output with `--rebuild` while emitting the normal envelope. Offline report command coverage includes compliance/security-audit sanitization plus compliance empty-cache retry cases for empty stdout, empty JSON, and Commander errors. | Keep leak checks, UID sanitization, and the empty-cache retry behavior green on future Commander pins. |
| Password report | `supported` | 2026-04-29 live proof: `dsk report password-report` exit 0, sanitized envelope clean. | Keep leak checks and UID sanitization green on future Commander pins. |
| MSP managed-company writes | `preview-gated` / design-complete | W10 audit in `docs/MSP_FAMILY_DESIGN.md`: Commander 17.2.16 exposes `msp-add` (`MSPAddCommand`), `msp-update` (`MSPUpdateCommand`), and `msp-remove` (`MSPRemoveCommand`) for provision/update/delete. Offline Commander wrapper tests cover kwargs and guards. | Support lift requires MSP admin live proof, Commander import/adoption marker contract, sanitized create/update/clean-replan transcript, and disposable-MC delete proof with `--allow-delete`. Until then, supported DSK posture is discover/validate/plan/diff only. |
| DSK MCP server | `supported` | W21 adds `dsk-mcp`, stdio JSON-RPC tool registration, lifecycle/report/KSM-bus tool handlers, docs config template, and offline tests covering validate/plan/apply guard/report redaction/server init. | Live Commander service-provider proof is opt-in and separate from offline MCP support; keep secret redaction and `auto_approve` guard green. |
| `dsk run` Commander passthrough | `preview-gated` | W20 adds the offline CLI surface: requires `--provider commander`, delegates to the existing batch Commander helper, redacts stdout/stderr, optionally fingerprints UID-like output, and passes through Commander's exit code. Offline tests cover mock-provider exit 5, argv parsing, `--json`, sanitization, secret redaction, and rc passthrough. | Needs sanctioned live Commander proof before support claim; no live Commander execution was part of W20. |
| Commander Service Mode provider | `supported` offline mock / live-pending | `keeper_sdk/providers/service_client.py` implements REST API v2 async submit/poll/result with FILEDATA and 429 retry; `keeper_sdk/providers/commander_service.py` wires discover/apply and reuses CLI provider capability gaps. | No live Service Mode run claimed; live proof must use committed smoke/runbook credentials before lifting beyond offline transport support. |
| Commander coverage denominator | informational / manual-refresh | [`docs/COMMANDER_COVERAGE.md`](./COMMANDER_COVERAGE.md) is generated by `scripts/coverage/commander_coverage.py` from `docs/COMMANDER.md`, the committed capability snapshot, and `CommanderCliProvider` static command use. | Refresh manually after Commander pin, capability snapshot, or provider command-wiring changes; not a CI gate today. |
| Team/role report stubs | `upstream-gap` | W20 adds `dsk report team-report` and `dsk report role-report` commands that fail closed with `CapabilityError`; next actions are `keeper enterprise-info --teams` and `keeper enterprise-info --roles`. | Lift only when Commander exposes a proven enumerable/reportable team and role surface with redaction/leak tests and live proof. |

P21-P24 acceptance checkpoints:

| Phase item | Acceptance | Evidence | Remaining bar |
|------------|------------|----------|---------------|
| P21 SharedFolder model / validate + P35 vaultSharingLifecycle | ACCEPTED offline | `VaultSharedFolder` / `diff_shared_folder` model path plus `tests/test_shared_folder_model.py` and `tests/test_vault_shared_folder.py`; P35 adds offline member create, guarded delete, and permission-update lifecycle cases. | Live Commander membership proof is blocked pending a second Keeper account; Commander write support remains preview-gated until live proof passes. |
| P22 module rename / back-compat window | `supported` | `declarative_sdk_k` compatibility shim now aliases submodule imports (`declarative_sdk_k.core`, providers, auth, CLI, secrets), emits a once-per-process `DeprecationWarning`, tags the legacy PAM `version` schema `$defs` entry with `x-keeper-deprecated`, and covers the local `.sync_baseline` Commander drift audit in `tests/test_compat_shim.py`. | Keep `keeper_sdk` import compatibility through the v1.x overlap; breaking removal waits for v2.0.0 and the two-version warning window. |
| P23 KSM app create proof | ACCEPTED for `bootstrap-ksm` | 2026-04-29 live bootstrap smoke passed: create/bind/share, config redemption, login probe, transcript leak check. `tests/test_ksm_app_lifecycle.py` keeps declarative app lifecycle out of supported claims until the manifest family grows a typed planner/apply path. | Full declarative KSM app lifecycle still needs schema/model/provider implementation, clean re-plan, and cleanup proof. |
| P24 docs / scaffold final sync | ACCEPTED | `SCAFFOLD.md`, `keeper_sdk/core/SCAFFOLD.md`, `RECONCILIATION.md`, and this plan reflect Phase 7 state. | Keep future sprint memos and operator orchestration out of `docs/`. |
| P34 SharedFolder destructive guard / permission breadth | ACCEPTED offline | `tests/test_shared_folder_commander.py` covers membership removal requiring `--allow-delete` and member `permission` transitions across `read_only`, `manage_records`, and `manage_users`. | Live readback proof remains required before full shared-folder lifecycle support. |

Order:

1. Extend capability mirror:
   - Keeper Commander non-PAM commands,
   - KSM Python SDK,
   - Keeper Terraform providers.
2. Generic vault records:
   - login records first,
   - custom fields and typed L1 field comparison are supported offline,
   - file attachment references are redacted stubs; binary upload remains an
     upstream-gap until redaction/size policy and Commander writer proof land.
3. Shared folders:
   - create/update,
   - memberships,
   - permission diffs,
   - destructive changes require explicit flags (membership removal guard offline-proven in P34).
4. KSM applications:
   - reference existing,
   - app create,
   - share binding,
   - client/token lifecycle with redaction.
5. Teams/roles/enterprise config:
   - read/validate first,
   - write only with upstream-safe surfaces and strong approval gates.
6. Compliance/reporting:
   - password-report is live-proven and supported,
   - security-audit-report is live-proven for the sanitized quiet envelope,
   - compliance-report is supported through the empty-cache auto-rebuild wrapper,
   - `dsk run` is preview-gated until live Commander passthrough proof,
   - team-report and role-report are upstream-gap stubs.

Acceptance:

- Every new surface enters with capability mirror evidence.
- Every mutating surface has mock tests, provider tests, docs, examples, and
  live smoke before support claim.

## Definition Of Done For "SDK Complete"

The SDK is complete when all are true:

- GitHub install path works (git URL or release wheel/sdist; see `docs/RELEASING.md`).
- Full local checks and GitHub CI are green.
- All modeled keys are supported, preview-gated, or upstream-gap.
- No preview-gated key silently applies or silently drops.
- Live smoke matrix is green for supported mutating surfaces.
- Unsupported capabilities fail in validate/plan/apply with clear next actions.
- Docs and scaffold match current behavior.
- GitHub issue state matches current behavior.

The SDK is not complete if:

- any supported feature needs `DSK_PREVIEW=1`,
- any mutating support lacks clean re-plan,
- any support claim depends on direct DAG writes,
- any live failure is classified as "probably fine" without a rerun,
- any secret-bearing transcript is required to debug normal failures.
