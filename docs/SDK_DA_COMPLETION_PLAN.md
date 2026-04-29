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
- **`keeper-vault.v1` L1 (scalar `login` slice): `supported`** — 2026-04-28 live
  proof (`vaultOneLogin` smoke PASSED create→verify→destroy; scalar field diff +
  apply converges). Full vault record-type surface elsewhere remains phased per
  `VAULT_L1_DESIGN` / parity tables.
- **MSP discover / `msp-environment.v1`:** 2026-04-28 live proof:
  `dsk validate --online` + `dsk plan` exit 0 against lab tenant using
  `tests/fixtures/examples/msp/01-minimal-msp.yaml`. Read-only discover + plan
  path confirmed. Commander `import` / `apply` for MSP remain unsupported and
  fail with `CapabilityError` until a committed write/marker contract exists.
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

**Acceptance (export / diff / password-report / security-audit-report /
compliance-report)** — satisfied 2026-04-29 on lab tenant plus offline
empty-cache wrapper coverage (see bullets above).

Recently unblocked:

- Nested `resources[].users[].rotation_settings`: **supported** for Commander
  17.2.16+ readback. GH#35 added `pam rotation list --record-uid --format json`;
  SDK discover now hydrates nested `pamUser.rotation_settings` from that JSON so
  post-apply re-plan can compare real Commander state instead of relying on
  missing-readback suppression. Top-level `users[].rotation_settings` remains
  outside this lift.

Not yet supported:
- Post-import RBI fields outside the P3.1 supported buckets: URL and proven
  typed booleans are supported / import-supported per `docs/COMMANDER.md`;
  list-shaped, audio-only, and upstream-gap rows stay explicitly out of
  supported claims.
- Standalone top-level `pamUser`.
- JIT writes.
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
into `discover()` for nested `pamUser.rotation_settings`. The nested
`resources[].users[]` slice is default-enabled without `DSK_PREVIEW` or
`DSK_EXPERIMENTAL_ROTATION_APPLY`.

### P2.1 Diagnose Rotation Drift

**Status:** 2026-04-29 supported for nested
`resources[].users[].rotation_settings` on Commander 17.2.16+. The former
upstream blocker was GH#35 (`pam rotation list` lacked UID filtering + JSON
output); Commander 17.2.16 unblocks the read path.

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
   json`; keep future live smoke transcripts as regression evidence, not as a
   gate on the already-supported nested slice.
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

- Only nested `resources[].users[].rotation_settings` is ungated for Commander
  17.2.16+ readback.
- Top-level `users[].rotation_settings` stays blocked.
- `default_rotation_schedule` stays blocked unless a separate setter/readback
  proof exists.

## Phase 3: Finish Post-Import Tuning / RBI

**2026-04-28 update:** E2E `pamRemoteBrowser` live smoke and `docs/live-proof/*rbi*`
on `main` **passed**; `docs/COMMANDER.md` has P3.1 buckets (URL from `rbiUrl` =
import-supported; DAG `allowedSettings` → `pam_settings.options` via
`TunnelDAG` = edit-supported-clean when a graph exists). “Finish” = align every
RBI **row** in `COMMANDER.md` with a bucket, keep list-shaped and audio-only
surfaces out of supported claims, and re-run smoke when the Commander pin
moves. Issue #5 closeout evidence: smoke rc=0 (`pamRemoteBrowser` create ->
verify -> clean re-plan -> destroy), committed sanitized artifact
`docs/live-proof/keeper-pam-environment.v1.89047920.rbi.sanitized.json`, and
COMMANDER P3.1 table buckets for each current RBI field.

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
3. Do not bundle connection fields with RBI fields if their readback behavior
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
  claimed as **import-supported** or **edit-supported-clean** must match
  `docs/COMMANDER.md` P3.1 rows and `test_rbi_readback.py` (and smoke where
  applicable). Fields that are **edit-supported-dirty** or **upstream-gap** stay
  explicit conflicts, preview, or out of `supported` table rows in the
  product matrix.
- Maintainer closeout checklist for GitHub #5: cite the sanitized RBI artifact,
  `COMMANDER.md` P3.1 table, `SDK_DA_COMPLETION_PLAN.md` Phase 3 acceptance,
  and `bash scripts/phase_harness/run_local_gates.sh`; do not paste raw logs or
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

Current classification: `upstream-gap`.

Tasks:

1. Re-check pinned Commander source before each release that might include JIT.
2. If a safe writer exists:
   - build pure mapping helper,
   - keep preview gate,
   - add mocked tests,
   - require live smoke.
3. If no safe writer exists:
   - keep `jit_settings` preview-gated,
   - update issue with source refs,
   - do not add apply shims.

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
| KSM application create | `supported` for `bootstrap-ksm`; general declarative app mutation remains a capability gap / `preview-gated` | 2026-04-29 live proof: `tests/live/test_ksm_bootstrap_smoke.py` exit 0 (1 passed); bootstrap create/bind/share, config redemption, login probe, and transcript leak check were clean. Offline bootstrap sequence has 3 cases. `tests/test_ksm_app_lifecycle.py` pins the current declarative boundary: `keeper-ksm.v1` validates as schema-only, rejects `ksm_apps`, and `plan` exits capability until a typed model/provider exists. | Needs declarative schema, typed loader, graph/diff/apply support, clean re-plan, and cleanup proof before claiming full KSM app lifecycle support. |
| KSM inter-agent bus | sealed stub / unsupported | `keeper_sdk/secrets/bus.py` exposes the API and frozen wire-format notes, but public methods raise `NotImplementedError` / `CapabilityError` with `next_action`. | No publish/subscribe support claim until protocol implementation and live proof land. |
| Teams/roles read-only validate | `preview-gated` | Offline validation rejects unknown PAM team/role resource types and accepts empty `keeper-enterprise.v1` team/role stubs. 2026-04-29 offline worker fixture: `tests/fixtures/teams_roles_manifest.yaml`; write-path decision: `docs/TEAMS_ROLES_WRITE_DESIGN.md`. No live tenant evidence was produced in that offline/no-network slice; current `dsk validate --online` for `keeper-enterprise.v1` remains a capability error before enterprise discovery. | Wire read-only `keeper-enterprise.v1` online discovery (`enterprise-info -t/-r --format json` or `api.query_enterprise`), run sanctioned live list/compare proof, then reconsider read-only support. Writes stay unsupported until an ownership model and approval gates are proven. |
| Compliance/security-audit reports | `supported` | 2026-04-29 `security-audit-report --sanitize-uids --quiet` live proof exited 0 with a JSON envelope. `compliance-report --sanitize-uids --quiet` hit Commander empty/non-JSON cache output; `--rebuild` emitted the expected envelope, and the SDK wrapper now auto-retries no-rebuild empty/error output with `--rebuild` while emitting the normal envelope. Offline report command coverage includes compliance/security-audit sanitization plus compliance empty-cache retry cases for empty stdout, empty JSON, and Commander errors. | Keep leak checks, UID sanitization, and the empty-cache retry behavior green on future Commander pins. |
| Password report | `supported` | 2026-04-29 live proof: `dsk report password-report` exit 0, sanitized envelope clean. | Keep leak checks and UID sanitization green on future Commander pins. |

P21-P24 acceptance checkpoints:

| Phase item | Acceptance | Evidence | Remaining bar |
|------------|------------|----------|---------------|
| P21 SharedFolder model / validate + P35 vaultSharingLifecycle | ACCEPTED offline | `VaultSharedFolder` / `diff_shared_folder` model path plus `tests/test_shared_folder_model.py` and `tests/test_vault_shared_folder.py`; P35 adds offline member create, guarded delete, and permission-update lifecycle cases. | Live Commander membership proof is blocked pending a second Keeper account; Commander write support remains preview-gated until live proof passes. |
| P22 module rename shim | ACCEPTED | `declarative_sdk_k` compatibility shim, `tests/test_compat_shim.py`, `pyproject.toml`, and `V1_GA_CHECKLIST.md` hardening row checked. | Keep `keeper_sdk` import shim for one minor cycle; breaking removal waits for v2.0.0. |
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
   - custom fields,
   - file attachments only after redaction/size policy.
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
   - compliance-report is supported through the empty-cache auto-rebuild wrapper.

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
