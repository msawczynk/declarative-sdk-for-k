## Sprint 7h-40 V5d — operator-bootstrap playbook for L2 + L4 (codex readonly memo)

You are a codex CLI **readonly** worker. Sprint 7h-38 deferred two slices because they require operator-supplied secrets:
- **L2** (parallel pamMachine vs profiles p1/p2/p3): needs `scripts/smoke/profiles/p1.json|p2.json|p3.json` + per-profile commander configs.
- **L4** (GH Actions matrix): needs operator-registered GH Actions secrets (`SDK_SMOKE_PROFILE_*_JSON`, `SDK_SMOKE_COMMANDER_CONFIG_*`, `SDK_SMOKE_KSM_CONFIG`).

Produce a single **operator-bootstrap playbook** that the operator can follow line-by-line (with commands, file paths, validation steps) to unblock both slices. The orchestrator will paste this directly into the user's queue once written.

# Required reading

1. `scripts/smoke/identity.py` — locate `SmokeProfile` dataclass + `load_profile()` introduced in 7h-37 S1.
2. `scripts/smoke/profiles/.gitignore` and `scripts/smoke/profiles/default.example.json` — schema for a profile JSON.
3. `scripts/smoke/sandbox.py` — locate `SandboxConfig.config_for_profile()`.
4. `scripts/smoke/parallel_guard.py` (introduced in 7h-38 L3) — locate `LockInfo`, `preflight_check()`, `acquire()`. Cite the lock-file path convention.
5. `scripts/smoke/README.md` — read the existing "Profiles" + "Concurrency / parallel profiles" sections.
6. `docs/sprint-memos/7h-37-S4-ci-matrix.codex.log` — the original L4 design memo (3763 lines; cite specific operator-action sections).
7. `docs/live-proof/README.md` — concurrency rule landed in 7h-38 L3.
8. `keeper_sdk/auth/helper.py` — `EnvLoginHelper` paths + `KEEPER_CONFIG`/`KEEPER_CONFIG_FILE` env-var honoring.
9. `tests/test_smoke_profile_load.py` — what a valid profile must satisfy.

# Deliverable: a single ~150-line markdown playbook

Structure:

## Section 1: Why this is operator-only

One paragraph: cite which secret each blocked slice needs and where the orchestrator cannot supply it (live tenant credentials, GitHub repo secrets API).

## Section 2: L2 prerequisites (lab tenant — 3 disjoint test users)

For each of `p1`, `p2`, `p3`:

1. **Create test user in tenant** — exact `keeper enterprise-user-add` command with placeholder values (email pattern: `msawczyn+sdk-p<N>@acme-demo.com` per LESSON `[orchestration][profile-discipline]`). Cite the lab tenant docs path.
2. **Provision shared folder + KSM app + project name** — exact CLI commands; show how to set them so they're DISJOINT per profile (different folder UID, different KSM app UID, different project name). Cite `scripts/smoke/sandbox.py` for what fields the sandbox reads.
3. **Generate Commander config** — `keeper login` per profile or `KEEPER_CONFIG_FILE=...` workflow; output paths `~/.keeper/p1.json`, `~/.keeper/p2.json`, `~/.keeper/p3.json` (or operator's preferred location).
4. **Drop the profile JSON** at `scripts/smoke/profiles/p<N>.json` matching the schema in `default.example.json`. Show a complete example (with placeholder values) so the operator just edits values, not structure.

Then validation steps:

5. `python3 -c "from scripts.smoke.identity import load_profile; print(load_profile('p1'))"` — must succeed.
6. `python3 scripts/smoke/smoke.py --scenario pamMachine --profile p1` — must run create→verify→destroy clean against p1's resources only.
7. Repeat for p2, p3.
8. `python3 scripts/smoke/smoke.py --scenario pamMachine --profile p1 --parallel-profile & python3 scripts/smoke/smoke.py --scenario pamMachine --profile p2 --parallel-profile & wait` — **the parallel guard from 7h-38 L3 must accept disjoint profiles**. Cite the lock dir path.

## Section 3: L4 prerequisites (GH Actions secrets)

For each secret:

1. **`SDK_SMOKE_PROFILE_P1_JSON`** — content = full profile JSON contents. Set via `gh secret set SDK_SMOKE_PROFILE_P1_JSON --body @scripts/smoke/profiles/p1.json`.
2. **`SDK_SMOKE_PROFILE_P2_JSON`**, **`SDK_SMOKE_PROFILE_P3_JSON`** — same.
3. **`SDK_SMOKE_COMMANDER_CONFIG_P1`**, **`...P2`**, **`...P3`** — content = base64 of `~/.keeper/p<N>.json`. Set via `gh secret set SDK_SMOKE_COMMANDER_CONFIG_P1 --body "$(base64 < ~/.keeper/p1.json)"`.
4. **`SDK_SMOKE_KSM_CONFIG`** — content = KSM application config JSON for the smoke harness's bootstrap. (Only needed if smoke uses KSM directly; cite the actual KSM-using code path if any.)

Validation:

5. `gh secret list` shows all 7 expected names.
6. Trigger the workflow manually via `gh workflow run smoke-matrix.yml -f profile=p1` (or whatever the matrix workflow is named per S4 memo) — verify GREEN per profile.
7. Trigger full matrix run; expect 3 parallel jobs, all GREEN.

## Section 4: Common pitfalls

Cite specific failure modes and recovery commands:

1. Commander config rewrite-in-place — operator must keep a backup before testing; cite `keeper_sdk/providers/commander_cli.py` for the rewrite path.
2. Cache DB collision — multiple Commander processes against the same `~/.keeper/` corrupt the cache; profile configs MUST live in disjoint paths. Cite `[orchestration][profile-config-isolation]` LESSON if it exists.
3. KSM marker version skew — if the lab tenant has older marker version on a record, smoke aborts. Cite `keeper_sdk/core/metadata.py:MARKER_VERSION` and the recovery command.
4. Parallel-guard refusal — the 5 refusal conditions from `scripts/smoke/parallel_guard.py:preflight_check()`. Cite each line and what the operator changes to satisfy.

## Section 5: Acceptance criteria for operator handoff back to orchestrator

A 5-bullet checklist the operator copies into the user's response queue when done:

- [ ] All 3 profile JSONs exist at `scripts/smoke/profiles/p<N>.json`.
- [ ] All 3 Commander configs exist at `~/.keeper/p<N>.json` (or operator-preferred path with the path documented in the profile JSON).
- [ ] Sequential single-profile smoke pass for all 3 profiles.
- [ ] Parallel-profile guard accepts disjoint pair (p1+p2).
- [ ] All 7 GH Actions secrets registered + matrix workflow GREEN.

When the operator pastes this checklist back checked, the orchestrator fires L2 and L4 in the same fan-out within ~10min wall.

## Section 6: CANDIDATE LESSON

`2026-04-27 [orchestration][operator-bootstrap-as-codex-deliverable] <one line>`.

# Constraints

- Read-only.
- Cite file:line for every non-trivial claim.
- Output the full playbook as your final response.
- Do not modify any files.
