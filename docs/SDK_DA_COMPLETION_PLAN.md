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
- Provider capability gaps surface as plan conflicts; `validate --online` now
  fails on provider capability gaps.
- GitHub/Codex task scaffolding exists, but remains manual and review-gated.

Not yet supported:

- Nested `resources[].users[].rotation_settings`: apply now reaches marker
  verification in live smoke, but post-apply re-plan still reports update drift
  for the nested `pamUser` and parent `pamMachine`.
- Post-import RBI tuning: live `pamRemoteBrowser` shows Commander writes RBI
  state to DAG `allowedSettings.connections`, while `discover()` does not read
  that state back into manifest-shaped fields.
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
7. A parent-reviewed live smoke proves the exact supported path.

Devil's advocate default: if any gate is ambiguous, keep the feature
`preview-gated`.

## Phase 0: Stabilize Current Branch

Goal: make the current dirty tree reviewable before more feature work.

Tasks:

1. Split review into coherent PR units if needed:
   - process/GitHub Codex scaffolding,
   - Commander provider rotation/discover fixes,
   - smoke scenario/docs,
   - validation/docs hardening.
2. Re-run focused checks:
   - `python3 -m pytest -q tests/test_cli.py tests/test_commander_cli.py tests/test_smoke_scenarios.py tests/test_smoke_args.py`
   - `python3 -m ruff check keeper_sdk/cli/main.py keeper_sdk/providers/commander_cli.py tests/test_cli.py tests/test_commander_cli.py`
   - `bash -n scripts/agent/codex_live_smoke.sh`
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

Current blocker: live apply reaches marker verification, but clean re-plan fails.

### P2.1 Diagnose Rotation Drift

Owner: Codex offline first, parent live proof.

Questions:

- Which fields differ on post-apply `pamUser`?
- Which fields differ on post-apply parent `pamMachine`?
- Are these actual missing writes, readback-shape gaps, or SDK-only placement
  metadata that should be ignored?
- Does `pam rotation edit` persist rotation in a Commander-readable surface, or
  only in a DAG/router surface the current `discover()` does not read?

Tasks:

1. Add an offline fixture reproducing post-apply live payload shape for nested
   `pamUser` + parent `pamMachine`.
2. Make drift output structured enough to identify exact field names in live
   smoke failure tails.
3. If fields are SDK-only linkage metadata, add them to the ignored drift set
   with a focused regression test.
4. If fields are real rotation settings, design readback before any gate lift.
5. Fix smoke cleanup if the managed Resources folder UID becomes stale after
   failed re-plan; cleanup must resolve by project name as fallback.

Focused tests:

- `tests/test_commander_cli.py`
- `tests/test_smoke_scenarios.py`
- `tests/test_cli.py` if exit behavior changes.

Live proof:

```bash
scripts/agent/codex_live_smoke.sh pamUserNestedRotation
```

Acceptance:

- Apply OK.
- Marker verification OK.
- Post-apply re-plan exits 0.
- Destroy plan shows deletes.
- Destroy apply OK.
- Final discover shows no SDK-owned records.

Gate-lift rule:

- Only nested `resources[].users[].rotation_settings` may be ungated.
- Top-level `users[].rotation_settings` stays blocked.
- `default_rotation_schedule` stays blocked unless a separate setter/readback
  proof exists.

## Phase 3: Finish Post-Import Tuning / RBI

Current blocker: Commander writes RBI settings into DAG
`allowedSettings.connections`, not into fields `discover()` maps today.

### P3.1 Split Tuning Claims

Classify each field as one of:

- `import-supported`: Commander import/extend owns it and discover reads it.
- `edit-supported-clean`: post-import edit writes it and discover reads it.
- `edit-supported-dirty`: post-import edit writes it but discover cannot read it.
- `upstream-gap`: no safe writer or no safe readback.

Tasks:

1. Update `docs/COMMANDER.md` with the classification.
2. Add tests that assert unsupported/dirty fields remain preview-gated.
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

- `pamRemoteBrowser` live smoke reaches clean re-plan for any field claimed as
  supported.
- Dirty/readback-gap fields remain explicit conflicts or preview-only.

## Phase 4: Close Deferred v1 Quality Gaps

Purpose: make "complete" mean robust, not just feature-rich.

Tasks:

1. Resolve remaining `xfail`s only when behavior exists:
   - Commander version mismatch gate.
   - Partial-apply rollback/reporting.
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
   - require parent live smoke.
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
   - destructive changes require explicit flags.
4. KSM applications:
   - reference existing,
   - app create,
   - share binding,
   - client/token lifecycle with redaction.
5. Teams/roles/enterprise config:
   - read/validate first,
   - write only with upstream-safe surfaces and strong approval gates.
6. Compliance/reporting:
   - start as read-only assertions in `validate --online`.

Acceptance:

- Every new surface enters with capability mirror evidence.
- Every mutating surface has mock tests, provider tests, docs, examples, and
  live smoke before support claim.

## Process Plan

### Codex / GitHub Work Queue

Use GitHub issues for hands-off work only when each issue has:

- task,
- hard scope,
- success criteria,
- allowed commands,
- live access policy,
- required `DONE` output.

Use `.github/workflows/codex-task.yml` for manual Codex Action runs after
`OPENAI_API_KEY` is configured. Keep `contents: read`; upload patch artifacts;
parent applies/reviews locally. Do not auto-push Codex output to `main`.

Local Codex:

- Use `--model gpt-5.5`.
- Use no network by default.
- Use `scripts/agent/codex_live_smoke.sh` only for one whitelisted smoke command.
- Smoke-only workers skip daybook/preamble to avoid token leaks.

### Parent Review Loop

For each task:

1. Read latest issue + relevant docs + latest live evidence.
2. Delegate narrow offline work to Codex.
3. Review diff before running broad checks.
4. Run focused tests.
5. Run one live proof only when the code is locally green.
6. Classify result: `supported`, `preview-gated`, or `upstream-gap`.
7. Update docs/scaffold/changelog/daybook.

Stop after three failed attempts on the same live blocker. Write down the exact
new blocker instead of continuing speculative patches.

## Definition Of Done For "SDK Complete"

The SDK is complete when all are true:

- GitHub install path works (git URL or release wheel/sdist; see `docs/RELEASING.md`).
- Full local checks and GitHub CI are green.
- All modeled keys are supported, preview-gated, or upstream-gap.
- No preview-gated key silently applies or silently drops.
- Live smoke matrix is green for supported mutating surfaces.
- Unsupported capabilities fail in validate/plan/apply with clear next actions.
- Docs and scaffold match current behavior.
- Daybook and issue state match current behavior.

The SDK is not complete if:

- any supported feature needs `DSK_PREVIEW=1`,
- any mutating support lacks clean re-plan,
- any support claim depends on direct DAG writes,
- any live failure is classified as "probably fine" without a rerun,
- any secret-bearing transcript is required to debug normal failures.
