# SDK Completion Plan

Goal: make `declarative-sdk-for-k` feature-complete against current Keeper functionality while keeping the SDK safe, deterministic, and agent-friendly.

Devil's-advocate execution gate: use
[`docs/SDK_DA_COMPLETION_PLAN.md`](./SDK_DA_COMPLETION_PLAN.md) as the
current completion contract when this roadmap conflicts with live evidence.

This plan is written for a parent orchestrator plus cheap Codex workers:

- Parent owns live-test design, credential boundaries, GitHub release assets, roadmap decisions, merge safety, and final review.
- Codex owns scoped implementation slices and can run live smoke only when explicitly delegated through a whitelisted harness command.
- Every Codex task returns a branch/patch, test output, caveats, and next steps. Parent verifies before merge.

## Current Baseline

Main branch as of 2026-04-25:

- `v1.0.0` GitHub release exists.
- **Distribution is GitHub only** (no PyPI): `publish.yml` attaches `dist/*` to
  each GitHub Release; install via git URL or downloaded wheel per `docs/RELEASING.md`.
- Local/core checks: **231 passed / 2 xfailed** (re-verify on current `main`),
  ruff, format, mypy, build/twine clean. CI is green across lint, mypy,
  py3.11/3.12/3.13 tests, examples, drift-check, and build.
- Commander provider supports current GA PAM lifecycle for manifests without preview keys.
- `EnvLoginHelper` supports Commander's step-based `LoginUi`, loads `KEEPER_CONFIG`, retries in-process `session_token_expired` once, and is live-proven for a full `pamMachine` create -> verify -> clean re-plan -> destroy cycle.
- First v1.1 slices landed:
  - `pamUserNested` offline smoke path.
  - `pam rotation edit` argv helper plus experimental apply wiring, still preview/experimental gated pending live proof.
  - `pam connection edit` / `pam rbi edit` apply wiring, still preview-gated pending live proof.
  - JIT and gateway-create / `projects[]` decisions captured as boundary/design docs; no gate removed.

Open GitHub issues:

- #4 Wire rotation settings after live proof.
- #5 Integrate post-import connection/RBI tuning.

Closed / classified:

- #3 Commander apply session refresh path: `supported` by PR #9 live smoke.
- #6 JIT support boundary: `upstream-gap`.
- #7 Gateway create and `projects[]`: design-only / `preview-gated`.

Latest #5 live proof:

- `python3 scripts/smoke/smoke.py --login-helper env --scenario pamRemoteBrowser` created records and teardown-only cleanup passed, but verify failed before re-plan: discovered `pamRemoteBrowser` payload did not expose `remote_browser_isolation=on`.
- Pinned Commander evidence: `pam rbi edit --remote-browser-isolation` writes DAG `allowedSettings.connections`, not a manifest-shaped field returned by current `discover()`.
- Classification remains `preview-gated` until readback/re-plan semantics are designed and proven.

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
5. **Codex can overfit fixtures.** Parent must review for silent drops, fake support, broad retries, and tests that assert implementation details instead of behavior.
6. **Release packaging is a dependency, not paperwork.** GitHub Release assets
   plus `twine check` in CI catch broken wheels before consumers pin a bad tag.
7. **Preview gates are product honesty.** Removing them is a user-facing support promise. Gate removal requires docs, tests, live proof, and clean re-plan.

Refined execution rule:

- A worker may add models, pure mappers, docs, and offline tests.
- A worker may not convert a capability from "preview/unsupported" to "supported" without parent-provided live proof.
- Parent must close each issue with one of three labels in the issue body: `supported`, `preview-gated`, or `upstream-gap`.
- "Complete" is reached when every discovered capability is in one of those three states and no manifest key is silently ignored.

Risk gates before merge:

| Risk | Required proof |
|------|----------------|
| New mutating provider path | unit tests + dry-run behavior + parent live smoke |
| Preview gate removal | live smoke + clean re-plan + docs/examples |
| New schema key | preview detector + provider conflict + docs |
| New retry path | bounded retry test + no retry for non-retryable errors |
| New external source in capability mirror | pinned version + drift-check CI |
| New secret/output path | redaction test |

## Operating Model

### Daybook and dedicated memory repo

Orchestration memory is **not** only in this repo: read
[`docs/DAYBOOK.md`](./DAYBOOK.md) for the GitHub daybook (`msawczynk/cursor-daybook`),
`sync_daybook.sh`, and the split between **main agent** (read/write/sync) and
**workers/subagents** (`AGENT_PREAMBLE.md`, silent read, lesson candidates).

### Cost-Optimized Orchestration And Checks

Cost target: spend cheap worker tokens on exploration/execution, spend parent tokens on review, gates, and decisions.

Worker tiers:

1. **Offline Codex implementation worker** — default for code/docs/tests. Runs focused tests only, no network, no live Keeper calls.
2. **Live Codex smoke worker** — allowed for cloud-code proof when parent gives one exact smoke command, enables network, and forbids secret/env printing. It may use existing lab credentials only through the smoke harness; it must not inspect or modify credential files except through the harness.
3. **Parent** — runs final diff review, full local checks once per integrated branch, classifies live results, updates issues/daybook, and merges/releases.

Check budget:

- Per worker: focused tests for touched area plus `ruff` on touched Python files.
- Per integration branch: one full `pytest`, `ruff`, `format --check`, `mypy`, build/twine, and drift-check only if capability mirror touched.
- Per PR: rely on GitHub matrix for py3.11/3.12/3.13 and build duplication; do not rerun full local suite after docs-only amendments unless risk changes.
- Per live feature: one clean live smoke create -> verify -> clean re-plan -> destroy before claiming `supported`.

Live smoke command rules:

- Use `python3 scripts/smoke/smoke.py ...` or another committed harness, never ad hoc Keeper mutations.
- Add `DSK_PREVIEW=1` / experimental env vars only when the issue says so.
- Redact stdout/stderr if a failure includes tokens, passwords, config JSON, or one-time codes.
- Parent reviews the transcript and closes the issue as `supported`, `preview-gated`, or `upstream-gap`.

### Parent Loop

For each work package:

1. Read issue, code, `JOURNAL.md`, and latest CI state.
2. Create/refresh a GitHub issue with acceptance criteria.
3. Spawn 1-3 Codex workers in isolated branches/worktrees.
4. Give each worker one narrow slice; if live proof is needed, give one whitelisted harness command, not credentials.
5. Review returned diff like a PR: correctness first, then tests/docs.
6. Run parent checks:
   - `python3 -m pytest -q`
   - `python3 -m ruff check .`
   - `python3 -m ruff format --check .`
   - `python3 -m mypy keeper_sdk`
   - `python3 -m build && python3 -m twine check dist/*`
   - `python3 scripts/sync_upstream.py --check` when capability mirror touched.
7. Open PR, wait CI, merge only green.
8. Parent delegates or runs live smoke for tenant-sensitive items, then reviews the transcript.
9. Update `CHANGELOG.md`, `SCAFFOLD.md`, issues, daybook.

### Codex Rules

Codex must:

- Work on one branch/worktree.
- Avoid live Keeper calls unless the parent explicitly delegates one whitelisted smoke harness command.
- Avoid secrets and credential files.
- Prefer offline unit tests and fixtures.
- Preserve public API/backward compatibility unless task says otherwise.
- Keep gates honest: do not remove preview/provider conflicts until apply is proven.
- Return exact commands run and exact files changed.

Codex must not:

- Change release tags.
- Push to `main`.
- Modify GitHub repo settings.
- Publish to PyPI (distribution is GitHub-only).
- Touch customer/lab private data unless parent supplies a sanitized fixture.
- Print env vars, credential JSON, TOTP seeds, passwords, KSM config contents, or raw secret-bearing logs.
- Convert plan-only helpers into live apply without explicit acceptance tests.

## Phase 0: Release / Publish Hygiene

### P0.1 GitHub Release assets (no PyPI)

Owner: parent.

Steps:

1. Confirm `.github/workflows/publish.yml` runs on `release: published`, runs
   `python -m build` + `twine check`, and uploads `dist/*` to the GitHub Release.
2. After the next tag, verify wheels/sdist appear on the release page.
3. Smoke install from git or wheel in a clean venv (`dsk --help`, `dsk validate
   examples/pamMachine.yaml`).

Acceptance:

- `docs/RELEASING.md` matches workflow behavior.
- Close or ignore historical **#1** (PyPI) as **out of scope** / cancelled.

Codex: no.

### P0.2 Signed Tag Policy

Owner: parent.

Steps:

1. Decide whether future tags require GPG/SSH signing.
2. Configure local signing outside repo only if user approves.
3. Document release tag policy in `docs/RELEASING.md`.

Acceptance:

- Future release checklist says annotated vs signed clearly.

Codex: docs-only slice possible after parent decides policy.

## Phase 1: Make Current PAM Apply Fully Proven

### P1.1 EnvLoginHelper Full Apply Smoke

Owner: parent for live smoke; Codex for smoke harness improvements.

Issue: #3.

Purpose: prove `--login-helper env` can run full `validate -> plan -> apply -> verify -> destroy`.

Parent live commands:

```bash
python3 scripts/smoke/smoke.py --login-helper env --scenario pamMachine
python3 scripts/smoke/smoke.py --login-helper env --scenario pamDatabase
python3 scripts/smoke/smoke.py --login-helper env --scenario pamDirectory
python3 scripts/smoke/smoke.py --login-helper env --scenario pamRemoteBrowser # #5 proof harness; latest live run exposes RBI readback gap
```

Codex task: add stronger smoke diagnostics.

Files:

- `scripts/smoke/smoke.py`
- `scripts/smoke/README.md`
- `tests/test_smoke_args.py`

Acceptance for Codex:

- Smoke logs show which auth path ran.
- Failure output preserves SDK stdout/stderr tail.
- No live calls in tests.
- `pytest tests/test_smoke_args.py tests/test_smoke_scenarios.py -q`

Parent acceptance:

- At least `pamMachine` full cycle passes with `--login-helper env`.
- If any scenario fails, failure is classified and issue updated.

### P1.2 Session Refresh Hardening

Owner: Codex for offline; parent for live.

Current state: one retry on `session_token_expired` landed.

Next Codex task:

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

Owner: Codex offline first.

Purpose: close DOR deferred scenarios.

Files:

- `keeper_sdk/core/diff.py`
- `keeper_sdk/core/planner.py`
- `keeper_sdk/providers/commander_cli.py`
- `tests/test_dor_scenarios.py`
- `tests/test_commander_cli.py`
- `V1_GA_CHECKLIST.md`

Codex tasks:

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

Parent live acceptance:

- Run adoption smoke against disposable sandbox after offline tests pass.

## Phase 2: Rotation

Issue: #4.

Current state:

- Manifest models include rotation pieces.
- Preview/provider gates still block support.
- `_build_pam_rotation_edit_args()` maps cron/on-demand basics.

### P2.1 Rotation Ref Resolution

Owner: Codex.

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
   - `resource_uid`: parent resource UID for nested user.
   - `config_uid`: synthetic config UID or resolved live config UID.
   - `admin_uid`: parent resource admin credential UID when declared.
3. Reject unsupported top-level user rotation unless explicit parent resource is modeled.

Acceptance:

- Unit tests cover nested user happy path.
- Unit tests cover missing parent, duplicate live match, missing config.
- No apply wiring yet.

### P2.2 Rotation Apply Wiring

Owner: Codex offline, parent live.

Implementation:

1. In `apply_plan`, after import/extend + discover + marker write, run rotation argv pass.
2. In dry-run, expose would-run rotation argv on the nested `pamUser` outcome without discover/execute.
3. Add outcome details for executed rotation commands.
4. Keep preview/provider gate until parent live proof passes.

Acceptance:

- `_run_cmd` receives `pam rotation edit ...` after record creation.
- Dry-run exposes deterministic argv and does not run it or discover live records.
- Non-zero Commander error becomes `CapabilityError` with next action.

Parent live proof:

- Create nested `pamUser` under `pamMachine`.
- Apply rotation cron/on-demand.
- Verify in tenant/Commander that rotation config changed.
- Only then remove gate for supported slice.

Latest live evidence:

- Experimental `pamUserNestedRotation` now reaches `pam rotation edit` with
  real record/config/resource UIDs after Users-folder discover and unique-title
  matching fixes.
- After routing rotation edit through the in-process Commander session, apply
  and marker verification pass. End-to-end support is still not proven because
  the post-apply re-plan reports updates for the nested `pamUser` and parent
  `pamMachine`; readback/drift semantics need to be designed before gate lift.

### P2.3 Rotation Gate Lift

Owner: Codex after parent live proof.

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

Owner: Codex.

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

Owner: Codex.

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

Owner: Codex offline; parent live.

Implementation:

- Run tuning pass after import/extend and before final re-plan.
- Add outcome details.
- Keep dry-run non-mutating.

Parent live proof:

- `pamRemoteBrowser` with RBI flags.
- `pamMachine`/`pamDatabase` with connection flags.
- Re-plan clean after apply.

Acceptance:

- Field drift for mapped fields closes.
- Unmapped fields still conflict.

## Phase 4: JIT

Issue: #6.

Risk: likely DAG/router-sensitive. Do not let Codex improvise live writer.

### P4.1 Boundary Research

Owner: Codex read-only.

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

Owner: Codex only if P4.1 finds safe path.

Acceptance:

- Pure helper + tests only.
- Preview/provider gates remain.

### P4.3 Apply + Gate Lift

Owner: parent live proof required.

Acceptance:

- Live tenant proof.
- Clean re-plan.
- Docs/examples.

## Phase 5: Gateway Create and Projects

Issue: #7.

### P5.1 Gateway Create Design

Owner: parent decision + Codex design doc.

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

Owner: Codex design; parent approval.

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

Owner: Codex.

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

Owner: Codex.

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

Owner: Codex offline, parent live.

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

Owner: Codex offline, parent live.

Scope:

- app create/reference
- share bindings
- client rotation
- output handling with redaction

Acceptance:

- No client secrets printed.
- Deterministic next-action for one-time tokens.

### P6.5 Teams, Roles, Enterprise Config

Owner: Codex after capability mirror.

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

Owner: design first.

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

## Codex Prompt Template

Use this exact shape for worker prompts:

```text
PREAMBLE: Read `/Users/martin/Downloads/.cursor/skills/AGENT_PREAMBLE.md` first and follow it.
Work in repo `/Users/martin/Downloads/Cursor tests/declarative-sdk-for-k`.

Task: <one narrow task>.

Context:
- Issue: #<n> <title>
- Current state: <short state>
- Do not use live Keeper credentials.
- Do not push to main.
- Do not remove preview/provider gates unless acceptance says so.

Files likely involved:
- <path>
- <path>

Acceptance:
- <behavior>
- <tests>
- <docs>

Commands to run:
- python3 -m pytest -q <focused tests>
- python3 -m ruff check <changed files>
- python3 -m ruff format --check <changed files>

Return:
DONE | branch=<branch> commits=<commits> tests=<summary> ruff=<summary>
CHG:
- <files + behavior>
CAVEATS:
- <unknowns>
NEXT:
- <exact parent merge/test/live step>
LESSONS ADDED:
- <none or text>
```

## First Five Codex Jobs

### Job A: Smoke Diagnostics for Env Helper

Issue: #3.

Prompt summary:

- Add auth-path and subprocess stderr/stdout diagnostics to smoke harness.
- No live calls.
- Tests in `tests/test_smoke_args.py`.

Parent after:

- Run `--login-helper env` live smoke.

### Job B: Session Retry Negative Tests

Issue: #3.

Prompt summary:

- Add tests for retry-once-only and no retry for non-session failures.
- Preserve context.

Parent after:

- Merge if CI green.

### Job C: Rotation Ref Resolver

Issue: #4.

Prompt summary:

- Add pure helper producing rotation argv entries from manifest + live records.
- No apply wiring.
- Tests only.

Parent after:

- Review model assumptions before wiring.

### Job D: Tuning Field Map Audit

Issue: #5.

Prompt summary:

- Produce docs table of import/tuning/unsupported fields.
- No behavior change.

Parent after:

- Decide supported first field subset.

### Job E: JIT Boundary Research

Issue: #6.

Prompt summary:

- Read Commander source and capability matrix.
- Return implementation/no-implementation decision with source links.
- No code unless obvious pure mapping helper.

Parent after:

- Decide whether JIT enters v1.1 or remains preview.

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

Stop and return to parent when:

- Live tenant needed.
- Credential/config needed.
- Upstream Commander behavior ambiguous.
- Feature requires direct DAG write.
- Existing public contract would break.
- Tests require broad fixture rewrite.
- More than three patch attempts fail.

## Parent Checklist Before Calling SDK Complete

- All open supportable capability issues closed or explicitly deferred with upstream evidence.
- `DSK_PREVIEW=1` only gates future/unproven keys.
- No supported manifest key silently drops on apply.
- Full local checks green.
- Main CI green.
- Live smoke matrix green for all supported mutating surfaces.
- GitHub Release asset workflow green on the latest tag.
- `README.md`, `SCAFFOLD.md`, `CHANGELOG.md`, `docs/CAPABILITY_MATRIX.md`, and daybook match reality.
