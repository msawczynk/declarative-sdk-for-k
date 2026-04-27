# SDK Completion Plan

Goal: make `declarative-sdk-for-k` feature-complete against current Keeper functionality while keeping the SDK safe, deterministic, and agent-friendly.

Devil's-advocate execution gate: use
[`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md) as the
current completion contract when this roadmap conflicts with live evidence.

## Current Baseline

Main branch as of 2026-04-27:

- `v1.0.0` GitHub release exists.
- **Distribution is GitHub only** (no PyPI): `publish.yml` attaches `dist/*` to
  each GitHub Release; install via git URL or downloaded wheel per `docs/RELEASING.md`.
- Local/core checks: **955 passed** on current `main` (re-run
  with `python3 -m pytest -q && python3 -m ruff check . && python3 -m ruff format --check . && python3 -m mypy keeper_sdk && python3 -m build && python3 -m twine check dist/*`),
  ruff, format, mypy, build/twine clean. CI is green across lint, mypy,
  py3.11/3.12/3.13 tests, examples, drift-check, and build.
- Commander provider supports current GA PAM lifecycle for manifests without preview keys.
- `EnvLoginHelper` supports Commander's step-based `LoginUi`, loads `KEEPER_CONFIG`, retries in-process `session_token_expired` once, and is live-proven for a full `pamMachine` create -> verify -> clean re-plan -> destroy cycle.
- First v1.1 slices landed:
  - `pamUserNested` offline smoke path.
  - `pam rotation edit` argv helper plus experimental apply wiring, still preview/experimental gated pending live proof.
  - `pam connection edit` / `pam rbi edit` apply wiring, still preview-gated pending live proof.
  - JIT and gateway-create / `projects[]` decisions captured as boundary/design docs; no gate removed.
- **`keeper-vault.v1` L1 (2026-04-27):** Commander discover/apply includes login **UPDATE** (record **version 3** JSON), `dsk validate --online`, and semantic scalar-login diff vs flattened live — still **preview / not PAM-bar GA** until live proof + `VAULT_L1_DESIGN` §7; see [README](../README.md) (Readiness table + **Honest limits — vault L1**).

Open GitHub issues:

- #4 Wire rotation settings after live proof.
- #5 Integrate post-import connection/RBI tuning.

Closed / classified:

- #3 Commander apply session refresh path: `supported` by PR #9 live smoke.
- #6 JIT support boundary: `upstream-gap`.
- #7 Gateway create and `projects[]`: design-only / `preview-gated`.

Latest #5 live proof (updated):

- Code: post-apply smoke builds `CommanderCliProvider(..., manifest_source=<temp yaml>)`; `discover()` best-effort bootstraps in-process params when RBI records exist so TunnelDAG merge can populate `pam_settings.options` (`remote_browser_isolation` / session recording tri-states). Commander exposes the target URL as field `rbiUrl` while the manifest uses `url` — `discover` maps that so re-plan is not spuriously dirty on URL alone. Offline partial overlay diff remains in `tests/test_rbi_readback.py`.
- **Live smoke (2026-04-28, `main` @ `975c777`):** `python3 scripts/smoke/smoke.py --scenario pamRemoteBrowser --login-helper profile` with Acme-lab KSM + profile → **SMOKE PASSED** (exit 0) — create, post-apply re-plan clean, destroy. Fixes **URL** readback: Commander field `rbiUrl` is merged into `url` in `discover()`. Warnings: post-destroy shared-folder sweeps may log `CommandError` (non-fatal in that run).
- **Schema evidence (2026-04-28):** `docs/live-proof/keeper-pam-environment.v1.89047920.rbi.sanitized.json` + `x-keeper-live-proof.evidence` updated on `pam-environment.v1` (alongside the machine transcript). **#5 / DA closeout (remaining):** maintainer pass on `docs/COMMANDER.md` P3.1 table + `SDK_DA_COMPLETION_PLAN.md` Phase 3 (buckets and DAG caveats) — copy is **landed**; open GitHub **#5** until the issue body is updated or closed with sign-off.
- Classification: **E2E `pamRemoteBrowser` smoke** is live-proven; **per-field** support labels are tabulated in COMMANDER/DA, not in this **Issue #5** paragraph alone.

## Definition Of Complete

Complete does not mean "schema accepts every imaginable future key." Complete means:

1. Every Keeper capability that the pinned upstream Commander / SDK / Terraform providers can safely drive is represented in manifest models, plan output, provider capability checks, apply behavior, docs, and tests.
2. Unsupported upstream capability is explicit: preview gate, plan conflict, clear `next_action`, or design issue.
3. Every mutating path is dry-runnable, idempotent, and ownership-safe.
4. Live tenant smoke exists for each supported mutating surface.
5. Machine-readable contracts stay stable: exit codes, plan JSON, schema version, redaction rules.

## Devil's Advocate Refinement

The fastest way to make this SDK worse is to chase "complete" as a feature-count target. This project must optimize for truthful support over breadth.

Hard objections:

1. **Upstream may not expose safe writers for every Keeper surface.** If Commander / SDK / Terraform only reads a feature, this SDK must not invent unsupported writes.
2. **Live tenant proof is not optional for mutating support.** Offline tests prove mapping, not product behavior. No live proof means preview gate or conflict stays.
3. **Direct DAG writes are a trap.** They can make tests pass while bypassing Commander invariants. Treat direct DAG writes as forbidden unless a later design explicitly approves them.
4. **"Full Keeper surface" can explode scope.** PAM completion ships first; broader vault/team/enterprise surfaces need capability mirror evidence and separate release phases.
5. **Fixture-driven implementation can overfit fixtures.** Review must catch silent drops, fake support, broad retries, and tests that assert implementation details instead of behavior.
6. **Release packaging is a dependency, not paperwork.** GitHub Release assets
   plus `twine check` in CI catch broken wheels before consumers pin a bad tag.
7. **Preview gates are product honesty.** Removing them is a user-facing support promise. Gate removal requires docs, tests, live proof, and clean re-plan.

Refined execution rule:

- Models, pure mappers, docs, and offline tests do not establish mutating support
  without live proof.
- A capability cannot move from "preview/unsupported" to "supported" without
  live proof.
- Each issue closes with one of three labels in the issue body: `supported`,
  `preview-gated`, or `upstream-gap`.
- "Complete" is reached when every discovered capability is in one of those three states and no manifest key is silently ignored.

Risk gates before merge:

| Risk | Required proof |
|------|----------------|
| New mutating provider path | unit tests + dry-run behavior + live smoke |
| Preview gate removal | live smoke + clean re-plan + docs/examples |
| New schema key | preview detector + provider conflict + docs |
| New retry path | bounded retry test + no retry for non-retryable errors |
| New external source in capability mirror | pinned version + drift-check CI |
| New secret/output path | redaction test |

## Phase 0: Release / Publish Hygiene

### P0.1 GitHub Release assets (no PyPI)

Steps:

1. Confirm `.github/workflows/publish.yml` runs on `release: published`, runs
   `python -m build` + `twine check`, and uploads `dist/*` to the GitHub Release.
2. After the next tag, verify wheels/sdist appear on the release page.
3. Smoke install from git or wheel in a clean venv (`dsk --help`, `dsk validate
   examples/pamMachine.yaml`).

Acceptance:

- `docs/RELEASING.md` matches workflow behavior.
- Close or ignore historical **#1** (PyPI) as **out of scope** / cancelled.

### P0.2 Signed Tag Policy

Steps:

1. Decide whether future tags require GPG/SSH signing.
2. Configure local signing outside repo only if user approves.
3. Document release tag policy in `docs/RELEASING.md`.

Acceptance:

- Future release checklist says annotated vs signed clearly.

## Phase 1: Make Current PAM Apply Fully Proven

### P1.1 EnvLoginHelper Full Apply Smoke

Issue: #3.

Purpose: prove `--login-helper env` can run full `validate -> plan -> apply -> verify -> destroy`.

Live smoke commands:

```bash
python3 scripts/smoke/smoke.py --login-helper env --scenario pamMachine
python3 scripts/smoke/smoke.py --login-helper env --scenario pamDatabase
python3 scripts/smoke/smoke.py --login-helper env --scenario pamDirectory
python3 scripts/smoke/smoke.py --login-helper env --scenario pamRemoteBrowser # #5; see docs/COMMANDER.md P3.1 for readback buckets
```

Task: add stronger smoke diagnostics.

Files:

- `scripts/smoke/smoke.py`
- `scripts/smoke/README.md`
- `tests/test_smoke_args.py`

Smoke diagnostics acceptance:

- Smoke logs show which auth path ran.
- Failure output preserves SDK stdout/stderr tail.
- No live calls in tests.
- `pytest tests/test_smoke_args.py tests/test_smoke_scenarios.py -q`

Live acceptance:

- At least `pamMachine` full cycle passes with `--login-helper env`.
- If any scenario fails, failure is classified and issue updated.

### P1.2 Session Refresh Hardening

Current state: one retry on `session_token_expired` landed.

Next task:

- Add tests for "retry once only, then fail with original context."
- Add test for non-session errors not retried.
- Ensure stderr/stdout context from first and second attempt is not lost.

Files:

- `keeper_sdk/providers/commander_cli.py`
- `tests/test_commander_cli.py`
- `docs/LOGIN.md`

Acceptance:

- No broad retry loops.
- CapabilityError context contains useful evidence.
- Full suite green.

### P1.3 Adoption / Field Drift / Two Writer Races

Purpose: close DOR deferred scenarios.

Files:

- `keeper_sdk/core/diff.py`
- `keeper_sdk/core/planner.py`
- `keeper_sdk/providers/commander_cli.py`
- `tests/test_dor_scenarios.py`
- `tests/test_commander_cli.py`
- `V1_GA_CHECKLIST.md`

Tasks:

1. Replace xfail DOR scenario for field drift with passing offline provider test.
2. Add adoption conflict tests:
   - unmanaged matching record -> adopt plan.
   - foreign marker -> conflict.
   - duplicate title -> collision.
3. Add two-writer race test:
   - clean plan, live marker changes before apply, apply refuses.

Acceptance:

- More `xfail` removed only when behavior really exists.
- No direct live calls.
- Plan JSON preserves conflict reason.

Live acceptance:

- Run adoption smoke against disposable sandbox after offline tests pass.

## Phase 2: Rotation

Issue: #4.

Current state:

- Manifest models include rotation pieces.
- Preview/provider gates still block support.
- `_build_pam_rotation_edit_args()` maps cron/on-demand basics.

### P2.1 Rotation Ref Resolution

Purpose: produce exact post-import rotation argv from manifest + live records.

Files:

- `keeper_sdk/providers/commander_cli.py`
- `tests/test_commander_cli.py`
- `keeper_sdk/core/models.py`

Implementation:

1. Add pure helper:
   - input: manifest/resource dict, plan changes, live records, synthetic config.
   - output: list of rotation argv entries.
2. Resolve:
   - `record_uid`: live `pamUser` UID.
   - `resource_uid`: containing resource UID for nested user.
   - `config_uid`: synthetic config UID or resolved live config UID.
   - `admin_uid`: containing resource admin credential UID when declared.
3. Reject unsupported top-level user rotation unless an explicit containing resource is modeled.

Acceptance:

- Unit tests cover nested user happy path.
- Unit tests cover missing containing resource, duplicate live match, missing config.
- No apply wiring yet.

### P2.2 Rotation Apply Wiring

Implementation:

1. In `apply_plan`, after import/extend + discover + marker write, run rotation argv pass.
2. In dry-run, expose would-run rotation argv on the nested `pamUser` outcome without discover/execute.
3. Add outcome details for executed rotation commands.
4. Keep preview/provider gate until live proof passes.

Acceptance:

- `_run_cmd` receives `pam rotation edit ...` after record creation.
- Dry-run exposes deterministic argv and does not run it or discover live records.
- Non-zero Commander error becomes `CapabilityError` with next action.

Live proof:

- Create nested `pamUser` under `pamMachine`.
- Apply rotation cron/on-demand.
- Verify in tenant/Commander that rotation config changed.
- Only then remove gate for supported slice.

Latest live evidence:

- Experimental `pamUserNestedRotation` now reaches `pam rotation edit` with
  real record/config/resource UIDs after Users-folder discover and unique-title
  matching fixes.
- After routing rotation edit through the in-process Commander session, apply
  and marker verification pass. **2026-04-28 Acme-lab** `pamUserNestedRotation`
  smoke: same outcome — re-plan `exit 2` with `update` rows (e.g. `pam_settings`
  on the parent `pamMachine`, `managed` on the nested `pamUser`). End-to-end
  support is still not proven; readback/drift semantics for rotation stay open
  (issue **#4**).

### P2.3 Rotation Gate Lift

Tasks:

- Remove `rotation_settings` from `PREVIEW_KEYS` only for supported modeled path.
- Remove provider conflict only for supported path.
- Keep `default_rotation_schedule` gated until real setter known.
- Update docs and examples.

Acceptance:

- Manifest with supported `users[].rotation_settings` validates without `DSK_PREVIEW`.
- Unsupported schedule/config/default cases still conflict clearly.

## Phase 3: Post-Import Connection / RBI Tuning

Issue: #5.

Current state: field map and offline-tested apply wiring exist, but support
remains preview-gated. Live `pamRemoteBrowser` proof showed Commander writes
RBI state into DAG `allowedSettings.connections`, which current `discover()`
does not read back as manifest-shaped drift state.

### P3.1 Tuning Field Map Audit

Task:

- Compare current models to Commander `pam connection edit` / `pam rbi edit` flags.
- Mark each field:
  - import-supported
  - tuning-supported
  - unsupported
  - unknown/live proof needed

Files:

- `docs/CAPABILITY_MATRIX.md`
- `docs/capability-snapshot.json`
- `keeper_sdk/core/models.py`
- `keeper_sdk/providers/commander_cli.py`
- `SCAFFOLD.md`

Acceptance:

- One docs section/table, no behavior change.
- No unsupported field silently claimed.

### P3.2 Tuning Ref Resolution

Implementation:

- Resolve record UID, config UID, admin/launch/autofill credential refs.
- Build tuning argv list after import/extend.
- Keep pure helper testable.

Tests:

- Connection fields map to expected args.
- RBI fields map to expected args.
- Missing refs raise deterministic error.
- No-op resource returns no commands.

### P3.3 Tuning Apply Wiring + Live Proof

Implementation:

- Run tuning pass after import/extend and before final re-plan.
- Add outcome details.
- Keep dry-run non-mutating.

Live proof:

- `pamRemoteBrowser` with RBI flags.
- `pamMachine`/`pamDatabase` with connection flags.
- Re-plan clean after apply.

Acceptance:

- Field drift for mapped fields closes.
- Unmapped fields still conflict.

## Phase 4: JIT

Issue: #6.

Risk: likely DAG/router-sensitive. Do not improvise a live writer.

### P4.1 Boundary Research

Task:

- Inspect pinned Commander source for JIT code paths.
- Identify whether Commander exposes a safe CLI/API writer.
- Identify required role/license gates.
- Produce exact design: no code unless path is clear.

Acceptance:

- Issue #6 updated with source paths and decision:
  - implement now
  - keep preview-gated
  - upstream gap

### P4.2 Offline Mapping Slice

Acceptance:

- Pure helper + tests only.
- Preview/provider gates remain.

### P4.3 Apply + Gate Lift

Live proof required.

Acceptance:

- Live tenant proof.
- Clean re-plan.
- Docs/examples.

## Phase 5: Gateway Create and Projects

Issue: #7.

### P5.1 Gateway Create Design

Decision needed:

- SDK creates gateways directly, or
- SDK produces scaffold/next-action for operator to create gateway, then switches to `reference_existing`.

Constraints:

- Gateway creation may require local gateway install/bootstrap.
- KSM app binding must stay explicit.
- No hidden long-running infra side effects.

Acceptance:

- Design doc says supported/non-supported path.
- Preview gate remains until live proof.

### P5.2 `projects[]` Semantics

Questions:

- Is `projects[]` a multi-environment batch file?
- Does each project have isolated folders/config/gateway refs?
- How do exit codes aggregate?
- How does partial apply rollback/report?

Acceptance:

- Schema design proposal.
- Migration/compat story.
- No implementation until approved.

## Phase 6: Broader Keeper Surface

This phase makes SDK complete beyond PAM.

### P6.1 Capability Mirror Expansion

Task:

- Extend `scripts/sync_upstream.py` to mirror:
  - KSM Python SDK capabilities.
  - Keeper Terraform provider resources.
  - Commander non-PAM verbs relevant to vault/shared folders/teams/roles.

Acceptance:

- Generated matrix distinguishes upstream source.
- CI drift-check covers all mirrored sources.
- No behavior change.

### P6.2 Generic Vault Records

Scope:

- record types, folders, custom fields, references, attachments if supported safely.

Files:

- `keeper_sdk/core/models.py`
- schema JSON
- normalize/import/export modules
- provider interfaces
- mock provider
- commander provider

Acceptance:

- Create/update/delete for owned generic records.
- Export/import round-trip.
- Redaction keeps secrets out of output.
- Live smoke with disposable records.

### P6.3 Shared Folders Full Lifecycle

Scope:

- create shared folder
- membership
- permissions
- record placement

Acceptance:

- Ownership-safe delete.
- Permission diffs visible.
- No accidental user removal without `--allow-delete`.

### P6.4 KSM Applications

Scope:

- app create/reference
- share bindings
- client rotation
- output handling with redaction

Acceptance:

- No client secrets printed.
- Deterministic next-action for one-time tokens.

### P6.5 Teams, Roles, Enterprise Config

Scope:

- teams
- roles
- role enforcements
- node placement
- SCIM/SSO config only if upstream supports safe writer.

Acceptance:

- Strong conflict behavior for enterprise-wide risky changes.
- Separate approval gate for destructive membership changes.

### P6.6 Compliance / Reporting As Manifest

Scope:

- read-only compliance assertions first.
- write support only if upstream safe.

Acceptance:

- `validate --online` can assert compliance posture.
- Apply only mutates explicitly supported settings.

## Phase 7: Product Quality

### P7.1 Schema Stability

Rules:

- Keep `pam-environment.v1` stable through v1.x.
- Add optional blocks, not breaking renames.
- Use preview gate for modeled-but-not-driven keys.
- Version bump only when existing valid manifests change meaning.

### P7.2 Error Quality

Tasks:

- Every provider failure includes:
  - reason
  - context stdout/stderr tail when available
  - next action
  - no secret leakage

Acceptance:

- Tests for representative errors.
- CLI output readable in both Rich and JSON modes.

### P7.3 Docs / Scaffold

Tasks:

- Keep `SCAFFOLD.md` in sync after every feature phase.
- Keep `README.md` status truthful.
- Keep `CHANGELOG.md` high signal.
- Keep examples runnable offline.

## PR / Release Cadence

Preferred PR size:

- 1 behavior slice.
- 1 focused issue.
- <= 8 files changed when possible.
- Tests + docs included.

Merge order:

1. #3 live apply proof + retry hardening.
2. #4 rotation resolver.
3. #5 tuning audit + resolver.
4. Rotation/tuning live wiring PRs.
5. #6 JIT boundary.
6. #7 gateway/projects design.
7. Broader non-PAM capability mirror.

Release cadence:

- `1.0.1`: publish/config/docs fix only if GitHub release/tag/doc cleanup needed.
- `1.1.0`: live-proven rotation/tuning/session-refresh + smoke coverage.
- `1.2.0`: gateway/create/projects/import-adopt improvements.
- `1.3.0+`: broader Keeper surfaces beyond PAM.

## Stop Conditions

Stop when:

- Live tenant needed.
- Credential/config needed.
- Upstream Commander behavior ambiguous.
- Feature requires direct DAG write.
- Existing public contract would break.
- Tests require broad fixture rewrite.
- More than three patch attempts fail.

## Checklist Before Calling SDK Complete

- All open supportable capability issues closed or explicitly deferred with upstream evidence.
- `DSK_PREVIEW=1` only gates future/unproven keys.
- No supported manifest key silently drops on apply.
- Full local checks green.
- Main CI green.
- Live smoke matrix green for all supported mutating surfaces.
- GitHub Release asset workflow green on the latest tag.
- `README.md`, `SCAFFOLD.md`, `CHANGELOG.md`, and `docs/CAPABILITY_MATRIX.md` match reality.
